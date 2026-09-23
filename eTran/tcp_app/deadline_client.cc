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

#include <iostream>
#include <string>

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
    while ((opt = getopt(argc, argv, "i:p:b:n:d:P:BS")) != -1) {
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
            default:
                std::cout << "Usage: " << argv[0] <<
                    " [-i server_ip, default:192.168.6.1]" <<
                    " [-p server_port, default:50000]" <<
                    " [-b request bytes, must match server -b, default:100]" <<
                    " [-n total bytes, default:1000000]" <<
                    " [-d deadline us, default:10000]" <<
                    " [-P priority, default:1]" <<
                    " [-B set parameters before connect()]" <<
                    " [-S stream: send back to back, do not wait for responses]" << std::endl;
                return -1;
        }
    }
    return 0;
}

int main(int argc, char *argv[])
{
    if (parse_args(argc, argv))
        return -1;

    int fd = socket(AF_INET, SOCK_STREAM, 0);
    if (fd < 0) {
        perror("socket");
        return -1;
    }

    uint64_t start_us = now_us();

    if (set_before_connect && set_params(fd))
        return -1;

    struct sockaddr_in addr = {};
    addr.sin_family = AF_INET;
    addr.sin_port = htons(server_port);
    addr.sin_addr.s_addr = inet_addr(server_ip_str.c_str());
    if (connect(fd, (struct sockaddr *)&addr, sizeof(addr))) {
        perror("connect");
        return -1;
    }

    if (!set_before_connect && set_params(fd))
        return -1;

    uint64_t xfer_start_us = now_us();
    char *buf = (char *)calloc(1, std::max(message_bytes, (unsigned int)SHORT_RESPONSE_SIZE));
    uint64_t sent = 0;
    while (sent < total_bytes) {
        if (xfer(fd, buf, message_bytes, true))
            return -1;
        if (!stream && xfer(fd, buf, SHORT_RESPONSE_SIZE, false))
            return -1;
        sent += message_bytes;
    }

    uint64_t end_us = now_us();
    uint64_t fct_us = end_us - start_us;
    uint64_t xfer_us = end_us - xfer_start_us;
    printf("sent %lu bytes, FCT %lu us, deadline %lu us, %s (slack %ld us)\n",
           sent, fct_us, deadline_us, fct_us <= deadline_us ? "MET" : "MISSED",
           (int64_t)deadline_us - (int64_t)fct_us);
    /* excludes connect(), comparable to delivery_rate in deadline_map */
    printf("transfer %lu us (connect %lu us), goodput %.1f Mbps\n",
           xfer_us, xfer_start_us - start_us, xfer_us ? sent * 8.0 / xfer_us : 0.0);

    free(buf);
    close(fd);
    return 0;
}
