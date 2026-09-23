/**
 * DeadlineTCP test client.
 *
 * Opens one connection to epoll_server, sets deadline/size/priority through
 * the DeadlineTCP API (before or after connect), then transfers total_bytes as
 * request/response rounds (or back to back with -S) and reports the completion
 * time against the deadline.
 */
#include <arpa/inet.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <unistd.h>
#include <errno.h>
#include <string.h>
#include <time.h>
#include <fcntl.h>

#include <algorithm>
#include <iostream>
#include <string>
#include <vector>

#include <deadline_tcp.h>

#define SHORT_RESPONSE_SIZE 100

std::string server_ip_str = "192.168.6.1";
uint16_t server_port = 50000;
unsigned int message_bytes = 100;
uint64_t total_bytes = 1000000;
uint64_t deadline_us = 10000;
uint32_t priority = 1;
bool set_before_connect = false;
/* write back to back without waiting for responses (backlogged sender) */
bool stream = false;
/* transfers to run, each on a new connection */
unsigned int repeats = 1;

static inline uint64_t now_us(void)
{
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (uint64_t)ts.tv_sec * 1000000 + ts.tv_nsec / 1000;
}

static int set_params(int fd)
{
    if (deadline_tcp_set_deadline(fd, deadline_us)) {
        fprintf(stderr, "deadline_tcp_set_deadline: %s\n", strerror(errno));
        return -1;
    }
    if (deadline_tcp_set_size(fd, total_bytes)) {
        fprintf(stderr, "deadline_tcp_set_size: %s\n", strerror(errno));
        return -1;
    }
    if (deadline_tcp_set_priority(fd, priority)) {
        fprintf(stderr, "deadline_tcp_set_priority: %s\n", strerror(errno));
        return -1;
    }
    printf("set deadline_us %lu total_bytes %lu priority %u (%s connect)\n",
           deadline_us, total_bytes, priority, set_before_connect ? "before" : "after");
    return 0;
}

static int xfer(int fd, char *buf, size_t len, bool is_write)
{
    size_t done = 0;
    while (done < len) {
        ssize_t ret = is_write ? write(fd, buf + done, len - done) : read(fd, buf + done, len - done);
        if (ret <= 0) {
            fprintf(stderr, "%s failed: %s\n", is_write ? "write" : "read", strerror(errno));
            return -1;
        }
        done += ret;
    }
    return 0;
}

int parse_args(int argc, char *argv[])
{
    int opt;
    while ((opt = getopt(argc, argv, "i:p:b:n:d:P:BSr:")) != -1) {
        switch (opt) {
            case 'i':
                server_ip_str = optarg;
                break;
            case 'p':
                server_port = std::stoi(optarg);
                break;
            case 'b':
                message_bytes = std::stoi(optarg);
                break;
            case 'n':
                total_bytes = std::stoull(optarg);
                break;
            case 'd':
                deadline_us = std::stoull(optarg);
                break;
            case 'P':
                priority = std::stoul(optarg);
                break;
            case 'B':
                set_before_connect = true;
                break;
            case 'S':
                stream = true;
                break;
            case 'r':
                repeats = std::stoul(optarg);
                break;
            default:
                std::cout << "Usage: " << argv[0] <<
                    " [-i server_ip, default:192.168.6.1]" <<
                    " [-p server_port, default:50000]" <<
                    " [-b request bytes, must match server -b, default:100]" <<
                    " [-n total bytes, default:1000000]" <<
                    " [-d deadline us, 0 = do not set deadline/size/priority (baseline), default:10000]" <<
                    " [-P priority, default:1]" <<
                    " [-B set parameters before connect()]" <<
                    " [-S stream: send back to back, do not wait for responses]" <<
                    " [-r repeat the transfer on new connections, default:1]" << std::endl;
                return -1;
        }
    }
    return 0;
}

struct run_result {
    uint64_t xfer_us;       /* first write until the last byte is delivered */
    uint64_t dl_us;         /* from setting the deadline until the last byte is delivered */
    uint64_t connect_us;
};

/* one connection: connect, (set parameters), transfer total_bytes */
static int run_once(struct run_result *r)
{
    int fd = socket(AF_INET, SOCK_STREAM, 0);
    if (fd < 0) {
        perror("socket");
        return -1;
    }

    bool use_deadline = deadline_us != 0;
    uint64_t start_us = now_us(), dl_start_us = 0;

    if (use_deadline && set_before_connect) {
        dl_start_us = now_us();
        if (set_params(fd))
            return -1;
    }

    struct sockaddr_in addr = {};
    addr.sin_family = AF_INET;
    addr.sin_port = htons(server_port);
    addr.sin_addr.s_addr = inet_addr(server_ip_str.c_str());
    if (connect(fd, (struct sockaddr *)&addr, sizeof(addr))) {
        perror("connect");
        return -1;
    }

    if (use_deadline && !set_before_connect) {
        dl_start_us = now_us();
        if (set_params(fd))
            return -1;
    }

    uint64_t xfer_start_us = now_us();
    char *buf = (char *)calloc(1, std::max(message_bytes, (unsigned int)SHORT_RESPONSE_SIZE));
    uint64_t sent = 0;
    if (stream) {
        /* non-blocking: send whatever fits, then drain responses so the
         * receive window never closes */
        if (fcntl(fd, F_SETFL, fcntl(fd, F_GETFL, 0) | O_NONBLOCK)) {
            fprintf(stderr, "fcntl O_NONBLOCK failed\n");
            return -1;
        }
        /* the server answers every message_bytes it receives: the last answer
         * means the last byte was delivered */
        uint64_t expect_resp = total_bytes % message_bytes == 0 ?
                               total_bytes / message_bytes * SHORT_RESPONSE_SIZE : 0;
        uint64_t resp = 0;
        char rbuf[65536];
        ssize_t ret;
        while (sent < total_bytes || resp < expect_resp) {
            if (sent < total_bytes) {
                ret = write(fd, buf, std::min((uint64_t)message_bytes, total_bytes - sent));
                if (ret < 0) {
                    fprintf(stderr, "write failed: %s\n", strerror(errno));
                    return -1;
                }
                sent += ret;
            }
            while ((ret = read(fd, rbuf, sizeof(rbuf))) > 0)
                resp += ret;
            if (ret < 0) {
                fprintf(stderr, "read failed: %s\n", strerror(errno));
                return -1;
            }
        }
    } else {
        while (sent < total_bytes) {
            if (xfer(fd, buf, message_bytes, true) || xfer(fd, buf, SHORT_RESPONSE_SIZE, false))
                return -1;
            sent += message_bytes;
        }
    }

    uint64_t end_us = now_us();
    r->xfer_us = end_us - xfer_start_us;
    r->connect_us = xfer_start_us - start_us;
    r->dl_us = use_deadline ? end_us - dl_start_us : 0;

    if (use_deadline)
        printf("sent %lu bytes in %lu us (deadline %lu us: %s, slack %ld us), transfer %lu us, goodput %.1f Mbps\n",
               sent, r->dl_us, deadline_us, r->dl_us <= deadline_us ? "MET" : "MISSED",
               (int64_t)deadline_us - (int64_t)r->dl_us, r->xfer_us, sent * 8.0 / r->xfer_us);
    else
        printf("sent %lu bytes (no deadline), transfer %lu us, goodput %.1f Mbps\n",
               sent, r->xfer_us, sent * 8.0 / r->xfer_us);

    free(buf);
    close(fd);
    return 0;
}

static uint64_t percentile(std::vector<uint64_t> v, double p)
{
    std::sort(v.begin(), v.end());
    return v[std::min(v.size() - 1, (size_t)(p / 100 * v.size()))];
}

int main(int argc, char *argv[])
{
    if (parse_args(argc, argv))
        return -1;
    if (stream && total_bytes % message_bytes)
        fprintf(stderr, "warning: -n is not a multiple of -b, completion is measured at the last write\n");

    std::vector<uint64_t> xfer, dl;
    unsigned int met = 0;
    for (unsigned int i = 0; i < repeats; i++) {
        struct run_result r;
        if (run_once(&r))
            return -1;
        xfer.push_back(r.xfer_us);
        if (deadline_us) {
            dl.push_back(r.dl_us);
            met += r.dl_us <= deadline_us;
        }
    }

    if (repeats > 1) {
        double mean = 0;
        for (auto x : xfer) mean += x;
        mean /= xfer.size();
        printf("SUMMARY runs %u bytes %lu deadline_us %lu | transfer_us mean %.0f p50 %lu p99 %lu max %lu | goodput_mean_Mbps %.1f",
               repeats, total_bytes, deadline_us, mean, percentile(xfer, 50), percentile(xfer, 99),
               percentile(xfer, 100), total_bytes * 8.0 / mean);
        if (deadline_us)
            printf(" | met %u/%u (miss ratio %.2f)", met, repeats, 1.0 - (double)met / repeats);
        printf("\n");
    }
    return 0;
}
