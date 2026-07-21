// sha256_compat.h — shim for libngu against modern MicroPython.
//
// Upstream MicroPython removed extmod/crypto-algorithms/sha256.h (it
// preceded today's per-port crypto and the MbedTLS option). libngu's
// ngu/k1.c includes that header for its non-mbedtls ECDH-hash path,
// using only sha256_init / sha256_update / sha256_final and the
// CRYAL_SHA256_CTX type.
//
// This shim re-exports those names against cifra's cf_sha256_* API
// (already linked in by NGU_NEEDS_CIFRA=1). Reachable to libngu via
// variants/<v>/makefile.wasm adding -I<repo>/cmd/coldcard-wasm/patches
// to CFLAGS_USERMOD. libngu's k1.c is patched (libngu-modern-mpy.patch)
// to include "sha256_compat.h" instead of the missing extmod header.

#ifndef SEEDHAMMER_SHA256_COMPAT_H
#define SEEDHAMMER_SHA256_COMPAT_H

#include <stddef.h>
#include "cifra/sha2.h"

typedef cf_sha256_context CRYAL_SHA256_CTX;

static inline void sha256_init(CRYAL_SHA256_CTX *ctx) {
    cf_sha256_init(ctx);
}

static inline void sha256_update(CRYAL_SHA256_CTX *ctx, const unsigned char *data, size_t len) {
    cf_sha256_update(ctx, data, len);
}

static inline void sha256_final(CRYAL_SHA256_CTX *ctx, unsigned char output[32]) {
    cf_sha256_digest_final(ctx, output);
}

#endif
