/**
 * DeadlineTCP application API.
 *
 * Applications include this header and run with LD_PRELOAD=libetran.so; the
 * calls below go through the interposed setsockopt() to the eTran library,
 * which forwards them to the microkernel (APPOUT_TCP_SET_DEADLINE). The
 * microkernel writes them into the per-connection eBPF map deadline_map.
 *
 * The parameters may be set before connect() (they are sent once the
 * connection is established) or at any time on a connected socket.
 * Without libetran.so, setsockopt() fails with ENOPROTOOPT.
 */
#pragma once

#include <stdint.h>
#include <sys/socket.h>

/* Arbitrary level unused by Linux */
#define SOL_DEADLINE_TCP 0x444c

/* uint64_t, deadline relative to the time of the call, in microseconds */
#define DTCP_DEADLINE_US 1
/* uint64_t, total bytes of the transfer */
#define DTCP_TOTAL_BYTES 2
/* uint32_t, priority, higher is more important */
#define DTCP_PRIORITY 3

static inline int deadline_tcp_set_deadline(int sockfd, uint64_t deadline_us)
{
    return setsockopt(sockfd, SOL_DEADLINE_TCP, DTCP_DEADLINE_US, &deadline_us, sizeof(deadline_us));
}

static inline int deadline_tcp_set_size(int sockfd, uint64_t total_bytes)
{
    return setsockopt(sockfd, SOL_DEADLINE_TCP, DTCP_TOTAL_BYTES, &total_bytes, sizeof(total_bytes));
}

static inline int deadline_tcp_set_priority(int sockfd, uint32_t priority)
{
    return setsockopt(sockfd, SOL_DEADLINE_TCP, DTCP_PRIORITY, &priority, sizeof(priority));
}
