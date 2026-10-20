/* POSIX host I/O for the Dong-native compiler; no parsing, checking or codegen. */
#define _GNU_SOURCE
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <limits.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

#define ABI __attribute__((sysv_abi))
#define MAX_FILES 4096
#define MAX_ROOTS 64
#define MAX_BYTES (16U * 1024U * 1024U)
#define MAX_FILE_BYTES (4U * 1024U * 1024U)
#define MAX_PATH_BYTES 16384
#define MAX_DIRECTORY_DEPTH 64
#define MAX_CATALOG_ENTRIES 131072
#define MAX_ARENA_MIB 1024

typedef struct { const void *p; uint64_t n; } Slice;
typedef struct { uint64_t root; Slice path, bytes; } Source;
typedef struct { uint64_t entry, roots, max_depth; } Options;
typedef struct {
    uint64_t tokens, nodes, strings, edges, types, fields, limbs, text, math_limbs, math_work;
} Limits;
typedef struct {
    Slice arena, sources, units, tokens, strings, nodes, edges, symbols, refs;
    Slice types, fields, node_types, values, value_states, limbs, layouts, field_offsets, info;
    uint64_t entry;
} Graph;
typedef struct {
    uint64_t status, exit_code, stage, code, detail, source, offset, used;
    Graph graph;
} Result;
typedef struct { uint64_t functions, instructions, arguments, text, piece, parameters, locations; } EmitLimits;
typedef struct { uint64_t status, stage, code, unit, node, detail, used, written; } EmitResult;
extern uint64_t ABI dong_native_emit(const Graph *, const EmitLimits *, uint64_t,
                                     uint8_t *, uint64_t, uint8_t *, uint64_t, EmitResult *);
_Static_assert(sizeof(EmitLimits) == 56 && sizeof(EmitResult) == 64, "Dong emit facade ABI");
_Static_assert(sizeof(void *) == 8 && sizeof(Source) == 40 && sizeof(Options) == 24 &&
               sizeof(Limits) == 80 && sizeof(Graph) == 296 && sizeof(Result) == 360,
               "Dong x86-64 frontend ABI");
extern uint64_t ABI dong_frontend_check(const Options *, const Source *, uint64_t,
                                      const Limits *, uint8_t *, uint64_t, Result *);
extern uint64_t ABI dong_frontend_diagnostic(const Source *, uint64_t, const Result *,
                                           uint8_t *, uint64_t, uint64_t *);
void ABI __attribute__((noreturn)) __dong_panic(uint32_t kind, uint32_t line,
                                              const void *file, uint64_t length) {
    (void)file; (void)length;
    fprintf(stderr, "dong-native: internal panic %u at line %u\n", kind, line);
    exit(2);
}

typedef struct {
    Source files[MAX_FILES];
    dev_t devices[MAX_FILES]; ino_t inodes[MAX_FILES];
    size_t count, total, entries;
    const char *entry;
    uint64_t entry_index;
} Catalog;
static void destroy(Catalog *c) {
    for (size_t i = 0; i < c->count; ++i) {
        free((void *)c->files[i].path.p); free((void *)c->files[i].bytes.p);
    }
}
static int error(const char *what, const char *path) {
    /* Paths can contain terminal control bytes: do not echo untrusted paths. */
    (void)path;
    fprintf(stderr, "dong-native: I/O error: %s (%s)\n", what, strerror(errno));
    return 0;
}
static int ends_dg(const char *name) {
    size_t n = strlen(name);
    return n > 3 && !strcmp(name + n - 3, ".dg");
}
static char *join(const char *prefix, const char *name) {
    size_t a = strlen(prefix), b = strlen(name);
    if (a > MAX_PATH_BYTES || b > MAX_PATH_BYTES || a + b + 1 > MAX_PATH_BYTES) {
        errno = ENAMETOOLONG; return NULL;
    }
    char *p = malloc(a + b + 2);
    if (!p) return NULL;
    memcpy(p, prefix, a);
    if (a && prefix[a - 1] != '/') p[a++] = '/';
    memcpy(p + a, name, b + 1);
    return p;
}
static int read_source(Catalog *c, int directory, const char *name,
                       const char *relative, const char *absolute, uint64_t root) {
    if (c->count == MAX_FILES) { errno = EFBIG; return error("source catalog limit", relative); }
    int fd = openat(directory, name, O_RDONLY | O_CLOEXEC | O_NOFOLLOW | O_NONBLOCK);
    if (fd < 0) return error("opening source", relative);
    struct stat before, after;
    if (fstat(fd, &before) || !S_ISREG(before.st_mode) || before.st_size < 0 ||
        (uintmax_t)before.st_size > MAX_FILE_BYTES ||
        (uintmax_t)before.st_size > MAX_BYTES - c->total) {
        close(fd); errno = EFBIG; return error("source must be a bounded regular file", relative);
    }
    size_t n = (size_t)before.st_size, at = 0;
    uint8_t *bytes = malloc(n ? n : 1);
    char *path = strdup(relative);
    if (!bytes || !path) { free(bytes); free(path); close(fd); return error("allocating source", relative); }
    while (at < n) {
        ssize_t got = read(fd, bytes + at, n - at);
        if (got < 0 && errno == EINTR) continue;
        if (got <= 0) { free(bytes); free(path); close(fd); errno = EIO; return error("reading source", relative); }
        at += (size_t)got;
    }
    uint8_t extra;
    ssize_t more;
    do { more = read(fd, &extra, 1); } while (more < 0 && errno == EINTR);
    int changed = more != 0 || fstat(fd, &after) || before.st_size != after.st_size ||
        before.st_mtim.tv_sec != after.st_mtim.tv_sec || before.st_mtim.tv_nsec != after.st_mtim.tv_nsec ||
        before.st_ctim.tv_sec != after.st_ctim.tv_sec || before.st_ctim.tv_nsec != after.st_ctim.tv_nsec;
    int closed = close(fd);
    if (changed || closed) { free(bytes); free(path); errno = EIO; return error("source changed while reading", relative); }
    c->files[c->count] = (Source){root, {path, strlen(path)}, {bytes, n}};
    if (!strcmp(absolute, c->entry)) {
        if (c->entry_index != UINT64_MAX) { free(bytes); free(path); errno = EINVAL; return error("entry occurs in overlapping roots", relative); }
        c->entry_index = c->count;
    }
    c->devices[c->count] = before.st_dev; c->inodes[c->count] = before.st_ino;
    ++c->count; c->total += n;
    return 1;
}
static int compare_names(const void *a, const void *b) {
    return strcmp(*(char *const *)a, *(char *const *)b);
}
static int walk(Catalog *c, int fd, const char *root_path, const char *prefix,
                uint64_t root, unsigned depth) {
    if (depth > MAX_DIRECTORY_DEPTH) { errno = ELOOP; return error("directory depth limit", prefix); }
    int duplicate = dup(fd);
    if (duplicate < 0) return error("duplicating directory", prefix);
    DIR *dir = fdopendir(duplicate);
    if (!dir) { close(duplicate); return error("opening directory", prefix); }
    char **names = NULL; size_t count = 0; int ok = 1;
    for (;;) {
        errno = 0; struct dirent *item = readdir(dir);
        if (!item) { if (errno) ok = error("reading directory", prefix); break; }
        if (!strcmp(item->d_name, ".") || !strcmp(item->d_name, "..")) continue;
        /* Bound even non-source directory entries, before growing a host list. */
        if (count == 65536 || c->entries == MAX_CATALOG_ENTRIES) { errno = EFBIG; ok = error("directory entry limit", prefix); break; }
        ++c->entries;
        char **next = realloc(names, (count + 1) * sizeof(*names));
        if (!next) { ok = error("allocating directory list", prefix); break; }
        names = next; names[count] = strdup(item->d_name);
        if (!names[count]) { ok = error("allocating directory name", prefix); break; }
        ++count;
    }
    if (closedir(dir)) ok = error("closing directory", prefix);
    if (count > 1) qsort(names, count, sizeof(*names), compare_names);
    for (size_t i = 0; i < count && ok; ++i) {
        struct stat st;
        if (fstatat(fd, names[i], &st, AT_SYMLINK_NOFOLLOW)) { ok = error("examining source entry", names[i]); break; }
        char *relative = join(prefix, names[i]);
        char *absolute = relative ? join(root_path, relative) : NULL;
        if (!relative || !absolute) { free(relative); free(absolute); ok = error("source path limit", names[i]); break; }
        if (S_ISLNK(st.st_mode)) {
            /* Explicitly reject child links, including directory escape/cycles. */
            errno = ELOOP; ok = error("symlinked source-root children are unsupported", relative);
        } else if (S_ISDIR(st.st_mode)) {
            int child = openat(fd, names[i], O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
            if (child < 0) ok = error("opening child directory", relative);
            else { ok = walk(c, child, root_path, relative, root, depth + 1); if (close(child)) ok = error("closing child directory", relative); }
        } else if (ends_dg(names[i])) {
            if (!S_ISREG(st.st_mode)) {
                errno = EINVAL; ok = error("source must be a regular file", relative);
            } else ok = read_source(c, fd, names[i], relative, absolute, root);
        }
        free(relative); free(absolute);
    }
    for (size_t i = 0; i < count; ++i) free(names[i]);
    free(names); return ok;
}
/* One-artifact publication: stage all bytes in the destination directory,
 * fsync the file, then replace the name atomically. Never truncate the target. */
static int publish_assembly(const char *output, const void *bytes, size_t length,
                            const Catalog *catalog) {
    char *copy = strdup(output);
    if (!copy) return error("allocating output path", output);
    char *slash = strrchr(copy, '/');
    const char *name = slash ? slash + 1 : copy;
    const char *parent = ".";
    if (slash) { *slash = 0; parent = *copy ? copy : "/"; }
    if (!*name || !strcmp(name, ".") || !strcmp(name, "..") || ends_dg(name)) {
        free(copy); errno = EINVAL; return error("output cannot overwrite a Dong source", output);
    }
    char *canonical = realpath(parent, NULL);
    if (!canonical) { free(copy); return error("resolving output directory", output); }
    int dir = open(canonical, O_RDONLY | O_DIRECTORY | O_CLOEXEC | O_NOFOLLOW);
    free(canonical);
    if (dir < 0) { free(copy); return error("opening output directory", output); }
    struct stat st;
    if (!fstatat(dir, name, &st, AT_SYMLINK_NOFOLLOW)) {
        if (!S_ISREG(st.st_mode)) { close(dir); free(copy); errno = EINVAL; return error("output must be a regular non-symlink file", output); }
        for (size_t i = 0; i < catalog->count; ++i) {
            if (st.st_dev == catalog->devices[i] && st.st_ino == catalog->inodes[i]) {
                close(dir); free(copy); errno = EINVAL; return error("output aliases a source file", output);
            }
        }
    } else if (errno != ENOENT) { close(dir); free(copy); return error("examining output", output); }
    char temporary[96]; int fd = -1;
    for (unsigned attempt = 0; attempt < 32; ++attempt) {
        snprintf(temporary, sizeof(temporary), ".dong-native-%ld-%u.tmp", (long)getpid(), attempt);
        fd = openat(dir, temporary, O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC | O_NOFOLLOW, 0600);
        if (fd >= 0 || errno != EEXIST) break;
    }
    if (fd < 0) { close(dir); free(copy); return error("staging assembly", output); }
    size_t at = 0; int ok = 1;
    while (at < length) {
        ssize_t n = write(fd, (const uint8_t *)bytes + at, length - at);
        if (n < 0 && errno == EINTR) continue;
        if (n <= 0) { ok = error("writing staged assembly", output); break; }
        at += (size_t)n;
    }
    if (ok && fsync(fd)) ok = error("syncing staged assembly", output);
    if (close(fd)) ok = error("closing staged assembly", output);
    if (ok && renameat(dir, temporary, dir, name)) ok = error("publishing assembly", output);
    if (!ok && unlinkat(dir, temporary, 0) && errno != ENOENT) error("removing failed staging file", output);
    if (close(dir)) ok = error("closing output directory", output);
    free(copy); return ok;
}
static int number(const char *text, uint64_t *out, uint64_t maximum) {
    if (!*text) return 0;
    uint64_t value = 0;
    for (const unsigned char *p = (const unsigned char *)text; *p; ++p) {
        if (*p < '0' || *p > '9' || value > (maximum - (*p - '0')) / 10) return 0;
        value = value * 10 + (*p - '0');
    }
    if (!value || value > maximum) return 0;
    *out = value; return 1;
}
static void usage(FILE *out) {
    fputs("usage: dong-native (--check | --emit-asm FILE) [--root DIR ...] [--stats]\n"
          "                   [--tokens N] [--nodes N] [--types N] [--fields N]\n"
          "                   [--limbs N] [--max-depth N] [--memory-mib N]\n"
          "                   [--mode debug|release] [--code-memory-mib N] [--assembly-mib N] SOURCE.dg\n"
          "POSIX x86-64 native compiler subset. --check writes no files.\n", out);
}
int main(int argc, char **argv) {
    char *roots[MAX_ROOTS] = {0}; size_t root_count = 0;
    const char *entry_arg = NULL, *output_arg = NULL; int check = 0, stats = 0, exit_code = 2;
    uint64_t emit_mode = 0, code_mib = 64, assembly_mib = 16;
    uint64_t arena_mib = 128, depth = 128;
    Limits limits = {131072, 65536, 4*1024*1024, 8192, 16384, 32768, 1048576, 4096, 256, 4096};
    Catalog catalog = {.entry_index = UINT64_MAX};
    char *entry = NULL; uint8_t *arena = NULL, *code_arena = NULL, *assembly = NULL;
    for (int i = 1; i < argc; ++i) {
        const char *arg = argv[i];
        if (!strcmp(arg, "--help")) { usage(stdout); exit_code = 0; goto done; }
        if (!strcmp(arg, "--check")) { check = 1; continue; }
        if (!strcmp(arg, "--stats")) { stats = 1; continue; }
        if (!strcmp(arg, "--emit-asm")) {
            if (++i == argc || output_arg) goto arguments;
            output_arg = argv[i]; continue;
        }
        if (!strcmp(arg, "--mode")) {
            if (++i == argc) goto arguments;
            if (!strcmp(argv[i], "debug")) emit_mode = 0;
            else if (!strcmp(argv[i], "release")) emit_mode = 1;
            else goto arguments;
            continue;
        }
        if (!strcmp(arg, "--root")) {
            if (++i == argc || root_count == MAX_ROOTS) goto arguments;
            char *root = realpath(argv[i], NULL);
            if (!root) { error("resolving source root", argv[i]); goto done; }
            size_t j = 0; while (j < root_count && strcmp(root, roots[j])) ++j;
            if (j == root_count) roots[root_count++] = root; else free(root);
            continue;
        }
        uint64_t *setting = NULL, maximum = 16*1024*1024;
        if (!strcmp(arg, "--memory-mib")) { setting = &arena_mib; maximum = MAX_ARENA_MIB; }
        else if (!strcmp(arg, "--code-memory-mib")) { setting = &code_mib; maximum = MAX_ARENA_MIB; }
        else if (!strcmp(arg, "--assembly-mib")) { setting = &assembly_mib; maximum = 256; }
        else if (!strcmp(arg, "--max-depth")) { setting = &depth; maximum = 256; }
        else if (!strcmp(arg, "--tokens")) setting = &limits.tokens;
        else if (!strcmp(arg, "--nodes")) setting = &limits.nodes;
        else if (!strcmp(arg, "--types")) setting = &limits.types;
        else if (!strcmp(arg, "--fields")) setting = &limits.fields;
        else if (!strcmp(arg, "--limbs")) setting = &limits.limbs;
        if (setting) {
            if (++i == argc || !number(argv[i], setting, maximum)) goto arguments;
            continue;
        }
        if (arg[0] == '-' || entry_arg) goto arguments;
        entry_arg = arg;
    }
    if ((!check && !output_arg) || (check && output_arg) || !entry_arg) goto arguments;
    struct stat entry_stat;
    if (lstat(entry_arg, &entry_stat) || !S_ISREG(entry_stat.st_mode)) {
        errno = EINVAL; error("entry must be a regular non-symlink file", entry_arg); goto done;
    }
    entry = realpath(entry_arg, NULL);
    if (!entry) { error("resolving entry", entry_arg); goto done; }
    catalog.entry = entry;
    if (!root_count) {
        char *slash = strrchr(entry, '/');
        const char *name = slash ? slash + 1 : entry;
        if (!ends_dg(name)) { errno = EINVAL; error("entry requires .dg suffix", entry); goto done; }
        if (!read_source(&catalog, AT_FDCWD, entry, name, entry, UINT64_MAX)) goto done;
    } else for (size_t i = 0; i < root_count; ++i) {
        int fd = open(roots[i], O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
        if (fd < 0) { error("opening source root", roots[i]); goto done; }
        int ok = walk(&catalog, fd, roots[i], "", i, 0);
        if (close(fd)) ok = error("closing source root", roots[i]);
        if (!ok) goto done;
    }
    if (catalog.entry_index == UINT64_MAX) { errno = EINVAL; error("entry is outside source roots", entry); goto done; }
    arena = malloc((size_t)arena_mib * 1024 * 1024);
    if (!arena) { error("allocating frontend workspace", entry); goto done; }
    Options options = {catalog.entry_index, root_count, depth}; Result result = {0};
    uint64_t status = dong_frontend_check(&options, catalog.files, catalog.count, &limits,
                                         arena, arena_mib * 1024 * 1024, &result);
    if (status != result.status || status == 1 || result.exit_code > 2) {
        fputs("dong-native: invalid frontend ABI result\n", stderr); goto done;
    }
    exit_code = (int)result.exit_code;
    if (status) {
        uint8_t diagnostic[MAX_PATH_BYTES + 1024]; uint64_t written = 0;
        uint64_t rendered = dong_frontend_diagnostic(catalog.files, catalog.count, &result,
                                                    diagnostic, sizeof(diagnostic), &written);
        if (!rendered && written <= sizeof(diagnostic)) {
            if (fwrite(diagnostic, 1, (size_t)written, stderr) != written) exit_code = 2;
        } else fprintf(stderr, "dong-native: frontend failure stage=%" PRIu64 " code=%" PRIu64
                       " detail=%" PRIu64 " offset=%" PRIu64 "\n", result.stage, result.code, result.detail, result.offset);
    }
    uint64_t backend_run = 0; EmitResult er = {0};
    if (!status && output_arg) {
        code_arena = malloc((size_t)code_mib * 1024 * 1024);
        assembly = malloc((size_t)assembly_mib * 1024 * 1024);
        if (!code_arena || !assembly) { error("allocating backend workspace", entry); exit_code = 2; goto done; }
        EmitLimits el = {4096, 262144, 131072, assembly_mib*1024*1024, 2048, 512, 1024};
        backend_run = 1;
        uint64_t emitted = dong_native_emit(&result.graph, &el, emit_mode, code_arena,
                                            code_mib*1024*1024, assembly, assembly_mib*1024*1024, &er);
        if (emitted != er.status || emitted == 1 || er.written > assembly_mib*1024*1024) {
            fputs("dong-native: invalid backend ABI result\n", stderr); exit_code = 2;
        } else if (emitted) {
            fprintf(stderr, "dong-native: backend failure status=%" PRIu64 " stage=%" PRIu64
                    " code=%" PRIu64 " unit=%" PRIu64 " node=%" PRIu64 " detail=%" PRIu64 "\n",
                    emitted, er.stage, er.code, er.unit, er.node, er.detail);
            exit_code = emitted == 3 || emitted == 4 ? 1 : 2;
        } else if (!publish_assembly(output_arg, assembly, (size_t)er.written, &catalog)) exit_code = 2;
    }
    if (stats) {
        int n = printf("{\"status\":%" PRIu64 ",\"exit_code\":%d,\"stage\":%" PRIu64
                       ",\"code\":%" PRIu64 ",\"catalog_files\":%zu,\"source_bytes\":%zu,\"arena_bytes\":%" PRIu64
                       ",\"used_bytes\":%" PRIu64 ",\"units\":%" PRIu64 ",\"tokens\":%" PRIu64 ",\"nodes\":%" PRIu64
                       ",\"types\":%" PRIu64 ",\"fields\":%" PRIu64 ",\"limbs\":%" PRIu64 ",\"strings\":%" PRIu64
                       ",\"backend_run\":%" PRIu64 ",\"backend_status\":%" PRIu64
                       ",\"backend_used_bytes\":%" PRIu64 ",\"assembly_bytes\":%" PRIu64 "}\n",
                       status, exit_code, result.stage, result.code, catalog.count, catalog.total,
                       arena_mib*1024*1024, result.used, result.graph.units.n, result.graph.tokens.n, result.graph.nodes.n,
                       result.graph.types.n, result.graph.fields.n, result.graph.limbs.n, result.graph.strings.n,
                       backend_run, er.status, er.used, er.written);
        if (n < 0 || fflush(stdout)) exit_code = 2;
    }
    goto done;
arguments:
    usage(stderr);
done:
    free(assembly); free(code_arena); free(arena); free(entry); destroy(&catalog);
    for (size_t i = 0; i < root_count; ++i) free(roots[i]);
    return exit_code;
}
