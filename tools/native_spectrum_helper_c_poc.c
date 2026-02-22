#define _POSIX_C_SOURCE 200809L

#include <ctype.h>
#include <errno.h>
#include <fcntl.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#ifdef _WIN32
#include <io.h>
#include <windows.h>
#else
#include <sys/wait.h>
#include <unistd.h>
#endif

#define REQUEST_SCHEMA "tz_player.native_spectrum_helper_request.v1"
#define RESPONSE_SCHEMA "tz_player.native_spectrum_helper_response.v1"
#define HELPER_VERSION "c-poc-ffmpeg-v2"
#define FFMPEG_DECODE_RATE_HZ 44100

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

typedef struct {
    char *track_path;
    int mono_target_rate_hz;
    int hop_ms;
    int band_count;
    int max_frames;
    int beat_enabled;
    int beat_hop_ms;
    int beat_max_frames;
    int waveform_proxy_enabled;
    int waveform_hop_ms;
    int waveform_max_frames;
} Request;

typedef struct {
    int mono_rate;
    size_t mono_sample_count;
    float *mono_samples;
    int stereo_rate;
    size_t stereo_sample_count;
    float *left_samples;
    float *right_samples;
    int duration_ms;
} DecodedAudio;

typedef struct {
    int pos_ms;
    uint8_t *bands;
} SpectrumFrame;

typedef struct {
    int duration_ms;
    size_t frame_count;
    SpectrumFrame *frames;
} SpectrumResult;

typedef struct {
    int pos_ms;
    int strength_u8;
    int is_beat;
} BeatFrame;

typedef struct {
    int duration_ms;
    double bpm;
    size_t frame_count;
    BeatFrame *frames;
} BeatResult;

typedef struct {
    int pos_ms;
    int lmin;
    int lmax;
    int rmin;
    int rmax;
} WaveformProxyFrame;

typedef struct {
    int duration_ms;
    size_t frame_count;
    WaveformProxyFrame *frames;
} WaveformProxyResult;

static double now_ms(void) {
#ifdef _WIN32
    static LARGE_INTEGER freq = {0};
    LARGE_INTEGER counter;
    if (freq.QuadPart == 0) {
        if (!QueryPerformanceFrequency(&freq) || freq.QuadPart <= 0) {
            return 0.0;
        }
    }
    if (!QueryPerformanceCounter(&counter)) {
        return 0.0;
    }
    return ((double)counter.QuadPart * 1000.0) / (double)freq.QuadPart;
#else
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (double)ts.tv_sec * 1000.0 + (double)ts.tv_nsec / 1000000.0;
#endif
}

static uint32_t read_u32_le(const uint8_t *p) {
    return (uint32_t)p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16) |
           ((uint32_t)p[3] << 24);
}

static uint16_t read_u16_le(const uint8_t *p) {
    return (uint16_t)p[0] | ((uint16_t)p[1] << 8);
}

static int next_pow2_clamped(int value) {
    int size = 1;
    while (size < value) {
        size <<= 1;
    }
    if (size < 256) {
        size = 256;
    }
    if (size > 2048) {
        size = 2048;
    }
    return size;
}

static char *read_stdin_all(size_t *out_len) {
    size_t cap = 4096;
    size_t len = 0;
    char *buf = (char *)malloc(cap);
    if (!buf) {
        return NULL;
    }
    while (!feof(stdin)) {
        if (len + 2048 > cap) {
            cap *= 2;
            char *grown = (char *)realloc(buf, cap);
            if (!grown) {
                free(buf);
                return NULL;
            }
            buf = grown;
        }
        size_t n = fread(buf + len, 1, cap - len - 1, stdin);
        len += n;
        if (ferror(stdin)) {
            free(buf);
            return NULL;
        }
        if (n == 0) {
            break;
        }
    }
    buf[len] = '\0';
    if (out_len) {
        *out_len = len;
    }
    return buf;
}

static const char *find_key(const char *json, const char *key) {
    size_t key_len = strlen(key);
    const char *p = json;
    while ((p = strstr(p, key)) != NULL) {
        if (p > json && p[-1] == '"' && p[key_len] == '"') {
            return p - 1;
        }
        p += key_len;
    }
    return NULL;
}

static const char *skip_ws(const char *p) {
    while (p && *p && isspace((unsigned char)*p)) {
        p++;
    }
    return p;
}

static int json_extract_int(const char *json, const char *key, int *out_value) {
    const char *k = find_key(json, key);
    if (!k) {
        return 0;
    }
    const char *colon = strchr(k, ':');
    if (!colon) {
        return 0;
    }
    const char *p = skip_ws(colon + 1);
    char *endptr = NULL;
    long v = strtol(p, &endptr, 10);
    if (endptr == p) {
        return 0;
    }
    *out_value = (int)v;
    return 1;
}

static char *json_extract_object(const char *json, const char *key) {
    const char *k = find_key(json, key);
    if (!k) {
        return NULL;
    }
    const char *colon = strchr(k, ':');
    if (!colon) {
        return NULL;
    }
    const char *p = skip_ws(colon + 1);
    if (!p || *p != '{') {
        return NULL;
    }
    const char *start = p;
    int depth = 0;
    int in_string = 0;
    int escape = 0;
    while (*p) {
        char ch = *p;
        if (in_string) {
            if (escape) {
                escape = 0;
            } else if (ch == '\\') {
                escape = 1;
            } else if (ch == '"') {
                in_string = 0;
            }
        } else {
            if (ch == '"') {
                in_string = 1;
            } else if (ch == '{') {
                depth++;
            } else if (ch == '}') {
                depth--;
                if (depth == 0) {
                    size_t len = (size_t)(p - start + 1);
                    char *out = (char *)malloc(len + 1u);
                    if (!out) {
                        return NULL;
                    }
                    memcpy(out, start, len);
                    out[len] = '\0';
                    return out;
                }
                if (depth < 0) {
                    return NULL;
                }
            }
        }
        p++;
    }
    return NULL;
}

static char *json_extract_string(const char *json, const char *key) {
    const char *k = find_key(json, key);
    if (!k) {
        return NULL;
    }
    const char *colon = strchr(k, ':');
    if (!colon) {
        return NULL;
    }
    const char *p = skip_ws(colon + 1);
    if (!p || *p != '"') {
        return NULL;
    }
    p++;
    size_t cap = 256;
    size_t len = 0;
    char *out = (char *)malloc(cap);
    if (!out) {
        return NULL;
    }
    while (*p && *p != '"') {
        char ch = *p++;
        if (ch == '\\') {
            ch = *p++;
            if (ch == '\0') {
                free(out);
                return NULL;
            }
            if (ch == '"' || ch == '\\' || ch == '/') {
                /* keep ch */
            } else if (ch == 'b') {
                ch = '\b';
            } else if (ch == 'f') {
                ch = '\f';
            } else if (ch == 'n') {
                ch = '\n';
            } else if (ch == 'r') {
                ch = '\r';
            } else if (ch == 't') {
                ch = '\t';
            } else {
                free(out);
                return NULL;
            }
        }
        if (len + 2 > cap) {
            cap *= 2;
            char *grown = (char *)realloc(out, cap);
            if (!grown) {
                free(out);
                return NULL;
            }
            out = grown;
        }
        out[len++] = ch;
    }
    if (*p != '"') {
        free(out);
        return NULL;
    }
    out[len] = '\0';
    return out;
}

static int parse_request(const char *json, Request *req) {
    memset(req, 0, sizeof(*req));
    char *schema = json_extract_string(json, "schema");
    if (!schema || strcmp(schema, REQUEST_SCHEMA) != 0) {
        free(schema);
        return 0;
    }
    free(schema);
    req->track_path = json_extract_string(json, "track_path");
    if (!req->track_path) {
        return 0;
    }
    char *spectrum_obj = json_extract_object(json, "spectrum");
    if (spectrum_obj) {
        (void)json_extract_int(spectrum_obj, "mono_target_rate_hz", &req->mono_target_rate_hz);
        (void)json_extract_int(spectrum_obj, "hop_ms", &req->hop_ms);
        (void)json_extract_int(spectrum_obj, "band_count", &req->band_count);
        (void)json_extract_int(spectrum_obj, "max_frames", &req->max_frames);
    }
    if (req->mono_target_rate_hz == 0 &&
        !json_extract_int(json, "mono_target_rate_hz", &req->mono_target_rate_hz)) {
        req->mono_target_rate_hz = 11025;
    }
    if (req->hop_ms == 0 && !json_extract_int(json, "hop_ms", &req->hop_ms)) {
        req->hop_ms = 40;
    }
    if (req->band_count == 0 && !json_extract_int(json, "band_count", &req->band_count)) {
        req->band_count = 48;
    }
    if (req->max_frames == 0 && !json_extract_int(json, "max_frames", &req->max_frames)) {
        req->max_frames = 12000;
    }
    free(spectrum_obj);
    req->beat_enabled = 0;
    char *beat_obj = json_extract_object(json, "beat");
    if (beat_obj) {
        if (json_extract_int(beat_obj, "hop_ms", &req->beat_hop_ms)) {
            req->beat_enabled = 1;
        }
        (void)json_extract_int(beat_obj, "max_frames", &req->beat_max_frames);
    }
    if (!req->beat_enabled && json_extract_int(json, "beat_timeline_hop_ms", &req->beat_hop_ms)) {
        req->beat_enabled = 1;
    }
    if (req->beat_max_frames == 0 &&
        !json_extract_int(json, "beat_timeline_max_frames", &req->beat_max_frames)) {
        req->beat_max_frames = 12000;
    }
    free(beat_obj);
    req->waveform_proxy_enabled = 0;
    char *waveform_obj = json_extract_object(json, "waveform_proxy");
    if (waveform_obj) {
        if (json_extract_int(waveform_obj, "hop_ms", &req->waveform_hop_ms)) {
            req->waveform_proxy_enabled = 1;
        }
        (void)json_extract_int(waveform_obj, "max_frames", &req->waveform_max_frames);
    }
    if (!req->waveform_proxy_enabled &&
        json_extract_int(json, "waveform_proxy_hop_ms", &req->waveform_hop_ms)) {
        req->waveform_proxy_enabled = 1;
    }
    if (req->waveform_max_frames == 0 &&
        !json_extract_int(json, "waveform_proxy_max_frames", &req->waveform_max_frames)) {
        req->waveform_max_frames = 30000;
    }
    free(waveform_obj);
    if (req->hop_ms < 10) {
        req->hop_ms = 10;
    }
    if (req->band_count < 8) {
        req->band_count = 8;
    }
    if (req->max_frames < 1) {
        req->max_frames = 1;
    }
    if (req->beat_hop_ms < 10) {
        req->beat_hop_ms = 40;
    }
    if (req->beat_max_frames < 1) {
        req->beat_max_frames = 1;
    }
    if (req->waveform_hop_ms < 10) {
        req->waveform_hop_ms = 20;
    }
    if (req->waveform_max_frames < 1) {
        req->waveform_max_frames = 1;
    }
    return 1;
}

static void free_request(Request *req) {
    free(req->track_path);
    req->track_path = NULL;
}

static int path_has_suffix_ci(const char *path, const char *suffix) {
    if (!path || !suffix) {
        return 0;
    }
    size_t path_len = strlen(path);
    size_t suffix_len = strlen(suffix);
    if (suffix_len == 0 || path_len < suffix_len) {
        return 0;
    }
    const char *start = path + (path_len - suffix_len);
    for (size_t i = 0; i < suffix_len; i++) {
        if (tolower((unsigned char)start[i]) != tolower((unsigned char)suffix[i])) {
            return 0;
        }
    }
    return 1;
}

#ifdef _WIN32
static char *cmd_double_quote(const char *input) {
    if (!input) {
        return NULL;
    }
    size_t len = strlen(input);
    size_t cap = (len * 2u) + 3u;
    char *out = (char *)malloc(cap);
    if (!out) {
        return NULL;
    }
    size_t w = 0;
    out[w++] = '"';
    for (size_t i = 0; i < len; i++) {
        char ch = input[i];
        if (ch == '"') {
            out[w++] = '\\';
        }
        out[w++] = ch;
    }
    out[w++] = '"';
    out[w] = '\0';
    return out;
}
#endif

static int decode_wav_file(const char *path, DecodedAudio *out) {
    memset(out, 0, sizeof(*out));
    FILE *fp = fopen(path, "rb");
    if (!fp) {
        return 0;
    }
    if (fseek(fp, 0, SEEK_END) != 0) {
        fclose(fp);
        return 0;
    }
    long file_size = ftell(fp);
    if (file_size <= 44) {
        fclose(fp);
        return 0;
    }
    rewind(fp);
    uint8_t *buf = (uint8_t *)malloc((size_t)file_size);
    if (!buf) {
        fclose(fp);
        return 0;
    }
    if (fread(buf, 1, (size_t)file_size, fp) != (size_t)file_size) {
        free(buf);
        fclose(fp);
        return 0;
    }
    fclose(fp);

    if (memcmp(buf, "RIFF", 4) != 0 || memcmp(buf + 8, "WAVE", 4) != 0) {
        free(buf);
        return 0;
    }

    uint16_t audio_format = 0;
    uint16_t channels = 0;
    uint32_t sample_rate = 0;
    uint16_t bits_per_sample = 0;
    const uint8_t *data_ptr = NULL;
    uint32_t data_size = 0;

    size_t off = 12;
    while (off + 8 <= (size_t)file_size) {
        const uint8_t *chunk = buf + off;
        uint32_t chunk_size = read_u32_le(chunk + 4);
        size_t chunk_data_off = off + 8;
        size_t next = chunk_data_off + chunk_size + (chunk_size & 1u);
        if (next > (size_t)file_size) {
            break;
        }
        if (memcmp(chunk, "fmt ", 4) == 0 && chunk_size >= 16) {
            audio_format = read_u16_le(buf + chunk_data_off + 0);
            channels = read_u16_le(buf + chunk_data_off + 2);
            sample_rate = read_u32_le(buf + chunk_data_off + 4);
            bits_per_sample = read_u16_le(buf + chunk_data_off + 14);
        } else if (memcmp(chunk, "data", 4) == 0) {
            data_ptr = buf + chunk_data_off;
            data_size = chunk_size;
        }
        off = next;
    }

    if (!data_ptr || sample_rate == 0 || channels == 0) {
        free(buf);
        return 0;
    }
    if (audio_format != 1 || bits_per_sample != 16 || (channels != 1 && channels != 2)) {
        free(buf);
        return 0;
    }

    size_t bytes_per_frame = (size_t)channels * 2u;
    if (bytes_per_frame == 0 || data_size < bytes_per_frame) {
        free(buf);
        return 0;
    }
    size_t frame_count = data_size / bytes_per_frame;
    float *mono = (float *)malloc(sizeof(float) * frame_count);
    float *left_out = (float *)malloc(sizeof(float) * frame_count);
    float *right_out = (float *)malloc(sizeof(float) * frame_count);
    if (!mono || !left_out || !right_out) {
        free(mono);
        free(left_out);
        free(right_out);
        free(buf);
        return 0;
    }
    for (size_t i = 0; i < frame_count; i++) {
        const uint8_t *p = data_ptr + (i * bytes_per_frame);
        int16_t left = (int16_t)read_u16_le(p);
        int16_t right = (channels == 2) ? (int16_t)read_u16_le(p + 2) : left;
        float lf = (float)left / 32768.0f;
        float rf = (float)right / 32768.0f;
        left_out[i] = lf;
        right_out[i] = rf;
        mono[i] = (lf + rf) * 0.5f;
    }
    free(buf);

    out->mono_rate = (int)sample_rate;
    out->mono_sample_count = frame_count;
    out->mono_samples = mono;
    out->stereo_rate = (int)sample_rate;
    out->stereo_sample_count = frame_count;
    out->left_samples = left_out;
    out->right_samples = right_out;
    out->duration_ms = (int)((frame_count * 1000u) / sample_rate);
    if (out->duration_ms < 1) {
        out->duration_ms = 1;
    }
    return 1;
}

static int decode_ffmpeg_file(const char *path, DecodedAudio *out) {
    memset(out, 0, sizeof(*out));
#ifdef _WIN32
    char *quoted = cmd_double_quote(path);
    if (!quoted) {
        fprintf(stderr, "ffmpeg decode (win): cmd_double_quote failed\n");
        return 0;
    }
    const char *prefix = "ffmpeg -v error -i ";
    const char *suffix =
        " -vn -sn -dn -f s16le -acodec pcm_s16le -ac 2 -ar 44100 pipe:1";
    size_t cmd_len = strlen(prefix) + strlen(quoted) + strlen(suffix) + 1u;
    char *cmdline = (char *)malloc(cmd_len);
    if (!cmdline) {
        fprintf(stderr, "ffmpeg decode (win): malloc cmdline failed\n");
        free(quoted);
        return 0;
    }
    snprintf(cmdline, cmd_len, "%s%s%s", prefix, quoted, suffix);
    free(quoted);

    SECURITY_ATTRIBUTES sa;
    memset(&sa, 0, sizeof(sa));
    sa.nLength = sizeof(sa);
    sa.bInheritHandle = TRUE;

    HANDLE stdout_read = NULL;
    HANDLE stdout_write = NULL;
    if (!CreatePipe(&stdout_read, &stdout_write, &sa, 0)) {
        fprintf(stderr, "ffmpeg decode (win): CreatePipe failed err=%lu\n",
                (unsigned long)GetLastError());
        free(cmdline);
        return 0;
    }
    if (!SetHandleInformation(stdout_read, HANDLE_FLAG_INHERIT, 0)) {
        fprintf(stderr, "ffmpeg decode (win): SetHandleInformation failed err=%lu\n",
                (unsigned long)GetLastError());
        CloseHandle(stdout_read);
        CloseHandle(stdout_write);
        free(cmdline);
        return 0;
    }

    /* STARTF_USESTDHANDLES + bInheritHandles=TRUE requires inheritable std handles. */
    HANDLE null_err = CreateFileA("NUL", GENERIC_WRITE, FILE_SHARE_WRITE | FILE_SHARE_READ,
                                  &sa, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, NULL);
    if (null_err == INVALID_HANDLE_VALUE) {
        fprintf(stderr, "ffmpeg decode (win): CreateFileA(NUL stderr) failed err=%lu\n",
                (unsigned long)GetLastError());
        CloseHandle(stdout_read);
        CloseHandle(stdout_write);
        free(cmdline);
        return 0;
    }
    HANDLE null_in = CreateFileA("NUL", GENERIC_READ, FILE_SHARE_WRITE | FILE_SHARE_READ, &sa,
                                 OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, NULL);
    if (null_in == INVALID_HANDLE_VALUE) {
        fprintf(stderr, "ffmpeg decode (win): CreateFileA(NUL stdin) failed err=%lu\n",
                (unsigned long)GetLastError());
        CloseHandle(stdout_read);
        CloseHandle(stdout_write);
        CloseHandle(null_err);
        free(cmdline);
        return 0;
    }

    STARTUPINFOA si;
    PROCESS_INFORMATION pi;
    memset(&si, 0, sizeof(si));
    memset(&pi, 0, sizeof(pi));
    si.cb = sizeof(si);
    si.dwFlags = STARTF_USESTDHANDLES;
    si.hStdOutput = stdout_write;
    si.hStdError = null_err;
    si.hStdInput = null_in;

    BOOL created = CreateProcessA(
        NULL,
        cmdline,
        NULL,
        NULL,
        TRUE,
        CREATE_NO_WINDOW,
        NULL,
        NULL,
        &si,
        &pi);
    free(cmdline);
    CloseHandle(stdout_write);
    CloseHandle(null_err);
    CloseHandle(null_in);
    if (!created) {
        fprintf(stderr, "ffmpeg decode (win): CreateProcessA failed err=%lu\n",
                (unsigned long)GetLastError());
        CloseHandle(stdout_read);
        return 0;
    }

    size_t cap = 8192;
    size_t len = 0;
    uint8_t *raw = (uint8_t *)malloc(cap);
    if (!raw) {
        fprintf(stderr, "ffmpeg decode (win): malloc raw buffer failed\n");
        CloseHandle(stdout_read);
        TerminateProcess(pi.hProcess, 1);
        CloseHandle(pi.hThread);
        CloseHandle(pi.hProcess);
        return 0;
    }
    for (;;) {
        if (len + 4096 > cap) {
            cap *= 2;
            uint8_t *grown = (uint8_t *)realloc(raw, cap);
            if (!grown) {
                fprintf(stderr, "ffmpeg decode (win): realloc raw buffer failed\n");
                free(raw);
                CloseHandle(stdout_read);
                TerminateProcess(pi.hProcess, 1);
                CloseHandle(pi.hThread);
                CloseHandle(pi.hProcess);
                return 0;
            }
            raw = grown;
        }
        DWORD bytes_read = 0;
        BOOL ok = ReadFile(stdout_read, raw + len, (DWORD)(cap - len), &bytes_read, NULL);
        if (!ok) {
            DWORD err = GetLastError();
            if (err == ERROR_BROKEN_PIPE) {
                break;
            }
            fprintf(stderr, "ffmpeg decode (win): ReadFile failed err=%lu\n",
                    (unsigned long)err);
            free(raw);
            CloseHandle(stdout_read);
            TerminateProcess(pi.hProcess, 1);
            CloseHandle(pi.hThread);
            CloseHandle(pi.hProcess);
            return 0;
        }
        if (bytes_read == 0) {
            break;
        }
        len += (size_t)bytes_read;
    }
    CloseHandle(stdout_read);
    (void)WaitForSingleObject(pi.hProcess, INFINITE);
    DWORD exit_code = 1;
    if (!GetExitCodeProcess(pi.hProcess, &exit_code)) {
        fprintf(stderr, "ffmpeg decode (win): GetExitCodeProcess failed err=%lu\n",
                (unsigned long)GetLastError());
        free(raw);
        CloseHandle(pi.hThread);
        CloseHandle(pi.hProcess);
        return 0;
    }
    CloseHandle(pi.hThread);
    CloseHandle(pi.hProcess);
    if (exit_code != 0) {
        fprintf(stderr, "ffmpeg decode (win): ffmpeg exit_code=%lu\n",
                (unsigned long)exit_code);
        free(raw);
        return 0;
    }
    if (len < 4) {
        fprintf(stderr, "ffmpeg decode (win): insufficient PCM bytes len=%zu\n", len);
        free(raw);
        return 0;
    }

    size_t frame_count = len / 4u;
    float *mono = (float *)malloc(sizeof(float) * frame_count);
    float *left_out = (float *)malloc(sizeof(float) * frame_count);
    float *right_out = (float *)malloc(sizeof(float) * frame_count);
    if (!mono || !left_out || !right_out) {
        fprintf(stderr,
                "ffmpeg decode (win): output buffer allocation failed frame_count=%zu\n",
                frame_count);
        free(mono);
        free(left_out);
        free(right_out);
        free(raw);
        return 0;
    }
    for (size_t i = 0; i < frame_count; i++) {
        const uint8_t *p = raw + (i * 4u);
        int16_t left = (int16_t)read_u16_le(p);
        int16_t right = (int16_t)read_u16_le(p + 2u);
        float lf = (float)left / 32768.0f;
        float rf = (float)right / 32768.0f;
        left_out[i] = lf;
        right_out[i] = rf;
        mono[i] = (lf + rf) * 0.5f;
    }
    free(raw);

    out->mono_rate = FFMPEG_DECODE_RATE_HZ;
    out->mono_sample_count = frame_count;
    out->mono_samples = mono;
    out->stereo_rate = FFMPEG_DECODE_RATE_HZ;
    out->stereo_sample_count = frame_count;
    out->left_samples = left_out;
    out->right_samples = right_out;
    out->duration_ms = (int)((frame_count * 1000u) / (unsigned)FFMPEG_DECODE_RATE_HZ);
    if (out->duration_ms < 1) {
        out->duration_ms = 1;
    }
    return 1;
#else
    int stdout_pipe[2];
    if (pipe(stdout_pipe) != 0) {
        return 0;
    }
    pid_t pid = fork();
    if (pid < 0) {
        close(stdout_pipe[0]);
        close(stdout_pipe[1]);
        return 0;
    }
    if (pid == 0) {
        close(stdout_pipe[0]);
        if (dup2(stdout_pipe[1], STDOUT_FILENO) < 0) {
            _exit(127);
        }
        close(stdout_pipe[1]);

        int devnull = open("/dev/null", O_WRONLY);
        if (devnull >= 0) {
            (void)dup2(devnull, STDERR_FILENO);
            close(devnull);
        }

        char *const argv[] = {
            "ffmpeg",
            "-v",
            "error",
            "-i",
            (char *)path,
            "-vn",
            "-sn",
            "-dn",
            "-f",
            "s16le",
            "-acodec",
            "pcm_s16le",
            "-ac",
            "2",
            "-ar",
            "44100",
            "pipe:1",
            NULL,
        };
        execvp("ffmpeg", argv);
        _exit(127);
    }
    close(stdout_pipe[1]);

    size_t cap = 8192;
    size_t len = 0;
    uint8_t *raw = (uint8_t *)malloc(cap);
    if (!raw) {
        close(stdout_pipe[0]);
        (void)waitpid(pid, NULL, 0);
        return 0;
    }
    for (;;) {
        if (len + 4096 > cap) {
            cap *= 2;
            uint8_t *grown = (uint8_t *)realloc(raw, cap);
            if (!grown) {
                free(raw);
                close(stdout_pipe[0]);
                (void)waitpid(pid, NULL, 0);
                return 0;
            }
            raw = grown;
        }
        ssize_t n = read(stdout_pipe[0], raw + len, cap - len);
        if (n < 0) {
            if (errno == EINTR) {
                continue;
            }
            free(raw);
            close(stdout_pipe[0]);
            (void)waitpid(pid, NULL, 0);
            return 0;
        }
        if (n == 0) {
            break;
        }
        len += (size_t)n;
    }
    close(stdout_pipe[0]);

    int status = 0;
    if (waitpid(pid, &status, 0) < 0) {
        free(raw);
        return 0;
    }
    if (!WIFEXITED(status) || WEXITSTATUS(status) != 0) {
        free(raw);
        return 0;
    }
    if (len < 4) {
        free(raw);
        return 0;
    }

    size_t frame_count = len / 4u;
    float *mono = (float *)malloc(sizeof(float) * frame_count);
    float *left_out = (float *)malloc(sizeof(float) * frame_count);
    float *right_out = (float *)malloc(sizeof(float) * frame_count);
    if (!mono || !left_out || !right_out) {
        fprintf(stderr,
                "ffmpeg decode (%s): output buffer allocation failed frame_count=%zu\n",
#ifdef _WIN32
                "win",
#else
                "posix",
#endif
                frame_count);
        free(mono);
        free(left_out);
        free(right_out);
        free(raw);
        return 0;
    }
    for (size_t i = 0; i < frame_count; i++) {
        const uint8_t *p = raw + (i * 4u);
        int16_t left = (int16_t)read_u16_le(p);
        int16_t right = (int16_t)read_u16_le(p + 2u);
        float lf = (float)left / 32768.0f;
        float rf = (float)right / 32768.0f;
        left_out[i] = lf;
        right_out[i] = rf;
        mono[i] = (lf + rf) * 0.5f;
    }
    free(raw);

    out->mono_rate = FFMPEG_DECODE_RATE_HZ;
    out->mono_sample_count = frame_count;
    out->mono_samples = mono;
    out->stereo_rate = FFMPEG_DECODE_RATE_HZ;
    out->stereo_sample_count = frame_count;
    out->left_samples = left_out;
    out->right_samples = right_out;
    out->duration_ms = (int)((frame_count * 1000u) / (unsigned)FFMPEG_DECODE_RATE_HZ);
    if (out->duration_ms < 1) {
        out->duration_ms = 1;
    }
    return 1;
#endif
    return 0; /* defensive/unreachable: keeps MSVC control-flow analysis happy */
}

static int decode_audio_file(const char *path, DecodedAudio *out) {
    if (decode_wav_file(path, out)) {
        return 1;
    }
    if (path_has_suffix_ci(path, ".wav") || path_has_suffix_ci(path, ".wave")) {
        return 0;
    }
    return decode_ffmpeg_file(path, out);
}

static int resample_down_if_needed(DecodedAudio *audio, int target_rate_hz) {
    if (target_rate_hz <= 0 || audio->mono_rate <= 0 || audio->mono_sample_count == 0) {
        return 0;
    }
    if (audio->mono_rate <= target_rate_hz) {
        return 1;
    }
    double step = (double)audio->mono_rate / (double)target_rate_hz;
    if (step <= 1.0) {
        return 1;
    }
    size_t out_cap = (size_t)((double)audio->mono_sample_count / step) + 2;
    float *out = (float *)malloc(sizeof(float) * out_cap);
    if (!out) {
        return 0;
    }
    size_t out_count = 0;
    double idx = 0.0;
    while ((size_t)idx < audio->mono_sample_count && out_count < out_cap) {
        out[out_count++] = audio->mono_samples[(size_t)idx];
        idx += step;
    }
    free(audio->mono_samples);
    audio->mono_samples = out;
    audio->mono_sample_count = out_count;
    audio->mono_rate = target_rate_hz;
    audio->duration_ms =
        (int)((audio->mono_sample_count * 1000u) / (unsigned)audio->mono_rate);
    if (audio->duration_ms < 1) {
        audio->duration_ms = 1;
    }
    return 1;
}

static void free_decoded_audio(DecodedAudio *audio) {
    free(audio->mono_samples);
    free(audio->left_samples);
    free(audio->right_samples);
    memset(audio, 0, sizeof(*audio));
}

static uint8_t quantize_level(float normalized) {
    if (normalized < 0.0f) {
        normalized = 0.0f;
    }
    if (normalized > 1.0f) {
        normalized = 1.0f;
    }
    float curved = sqrtf(normalized);
    int v = (int)lroundf(curved * 255.0f);
    if (v < 0) {
        v = 0;
    }
    if (v > 255) {
        v = 255;
    }
    return (uint8_t)v;
}

static int compute_spectrum(const DecodedAudio *audio, const Request *req, SpectrumResult *out) {
    memset(out, 0, sizeof(*out));
    if (!audio || audio->mono_rate <= 0 || !audio->mono_samples || audio->mono_sample_count == 0) {
        return 0;
    }
    int hop_samples = (int)((double)audio->mono_rate * ((double)req->hop_ms / 1000.0));
    if (hop_samples < 1) {
        hop_samples = 1;
    }
    int window_size = next_pow2_clamped(hop_samples * 2);
    int band_count = req->band_count;
    float nyquist = ((float)audio->mono_rate * 0.5f) - 1.0f;
    if (nyquist < 100.0f) {
        nyquist = 100.0f;
    }
    float min_freq = 40.0f;
    float max_freq = nyquist < 5000.0f ? nyquist : 5000.0f;
    if (max_freq <= min_freq) {
        max_freq = min_freq + 1.0f;
    }
    float *coeffs = (float *)malloc(sizeof(float) * (size_t)band_count);
    float *hann = (float *)malloc(sizeof(float) * (size_t)window_size);
    float *window = (float *)malloc(sizeof(float) * (size_t)window_size);
    float *all_mags = NULL;
    int *positions = NULL;
    if (!coeffs || !hann || !window) {
        free(coeffs);
        free(hann);
        free(window);
        return 0;
    }
    for (int i = 0; i < window_size; i++) {
        if (window_size <= 1) {
            hann[i] = 1.0f;
        } else {
            hann[i] = 0.5f - 0.5f * cosf((2.0f * (float)M_PI * (float)i) /
                                          (float)(window_size - 1));
        }
    }
    if (band_count <= 1) {
        coeffs[0] = 2.0f;
    } else {
        float ratio = powf(max_freq / min_freq, 1.0f / (float)(band_count - 1));
        for (int b = 0; b < band_count; b++) {
            float freq = min_freq * powf(ratio, (float)b);
            int k = (int)(0.5f + (((float)window_size * freq) / (float)audio->mono_rate));
            float omega = (2.0f * (float)M_PI * (float)k) / (float)window_size;
            coeffs[b] = 2.0f * cosf(omega);
        }
    }

    size_t max_possible_frames =
        (audio->mono_sample_count + (size_t)hop_samples - 1) / (size_t)hop_samples;
    size_t frame_count = max_possible_frames;
    if (frame_count > (size_t)req->max_frames) {
        frame_count = (size_t)req->max_frames;
    }
    if (frame_count == 0) {
        free(coeffs);
        free(hann);
        free(window);
        return 0;
    }

    all_mags = (float *)malloc(sizeof(float) * frame_count * (size_t)band_count);
    positions = (int *)malloc(sizeof(int) * frame_count);
    if (!all_mags || !positions) {
        free(coeffs);
        free(hann);
        free(window);
        free(all_mags);
        free(positions);
        return 0;
    }

    float max_mag = 0.0f;
    for (size_t frame_idx = 0; frame_idx < frame_count; frame_idx++) {
        size_t start = frame_idx * (size_t)hop_samples;
        positions[frame_idx] = (int)((start * 1000u) / (unsigned)audio->mono_rate);
        for (int i = 0; i < window_size; i++) {
            size_t idx = start + (size_t)i;
            float sample = idx < audio->mono_sample_count ? audio->mono_samples[idx] : 0.0f;
            window[i] = sample * hann[i];
        }
        for (int b = 0; b < band_count; b++) {
            float coeff = coeffs[b];
            float s_prev = 0.0f;
            float s_prev2 = 0.0f;
            for (int i = 0; i < window_size; i++) {
                float s = window[i] + (coeff * s_prev) - s_prev2;
                s_prev2 = s_prev;
                s_prev = s;
            }
            float power = (s_prev2 * s_prev2) + (s_prev * s_prev) - (coeff * s_prev * s_prev2);
            float mag = (power > 0.0f) ? log1pf(power) : 0.0f;
            all_mags[(frame_idx * (size_t)band_count) + (size_t)b] = mag;
            if (mag > max_mag) {
                max_mag = mag;
            }
        }
    }
    if (max_mag <= 0.0f) {
        max_mag = 1.0f;
    }

    SpectrumFrame *frames = (SpectrumFrame *)calloc(frame_count, sizeof(SpectrumFrame));
    if (!frames) {
        free(coeffs);
        free(hann);
        free(window);
        free(all_mags);
        free(positions);
        return 0;
    }
    for (size_t frame_idx = 0; frame_idx < frame_count; frame_idx++) {
        frames[frame_idx].pos_ms = positions[frame_idx];
        frames[frame_idx].bands = (uint8_t *)malloc((size_t)band_count);
        if (!frames[frame_idx].bands) {
            for (size_t j = 0; j < frame_idx; j++) {
                free(frames[j].bands);
            }
            free(frames);
            free(coeffs);
            free(hann);
            free(window);
            free(all_mags);
            free(positions);
            return 0;
        }
        for (int b = 0; b < band_count; b++) {
            float mag = all_mags[(frame_idx * (size_t)band_count) + (size_t)b];
            frames[frame_idx].bands[b] = quantize_level(mag / max_mag);
        }
    }

    out->duration_ms = audio->duration_ms;
    out->frame_count = frame_count;
    out->frames = frames;

    free(coeffs);
    free(hann);
    free(window);
    free(all_mags);
    free(positions);
    return 1;
}

static int to_i8(float value) {
    if (value < -1.0f) {
        value = -1.0f;
    }
    if (value > 1.0f) {
        value = 1.0f;
    }
    int v = (int)lroundf(value * 127.0f);
    if (v < -127) {
        v = -127;
    }
    if (v > 127) {
        v = 127;
    }
    return v;
}

static double rms_energy_window(const float *values, size_t count) {
    if (!values || count == 0) {
        return 0.0;
    }
    double total = 0.0;
    for (size_t i = 0; i < count; i++) {
        double v = (double)values[i];
        total += v * v;
    }
    return sqrt(total / (double)count);
}

static int compute_beat(const DecodedAudio *audio, const Request *req, BeatResult *out) {
    memset(out, 0, sizeof(*out));
    if (!req->beat_enabled) {
        return 1;
    }
    if (!audio || audio->mono_rate <= 0 || !audio->mono_samples || audio->mono_sample_count == 0) {
        return 0;
    }

    int hop_ms = req->beat_hop_ms;
    if (hop_ms < 10) {
        hop_ms = 40;
    }
    int hop_samples = (int)((double)audio->mono_rate * ((double)hop_ms / 1000.0));
    if (hop_samples < 1) {
        hop_samples = 1;
    }
    int window_samples = hop_samples * 2;
    if (window_samples < hop_samples) {
        window_samples = hop_samples;
    }

    size_t max_frames = (size_t)req->beat_max_frames;
    double *energies = (double *)malloc(sizeof(double) * max_frames);
    double *onsets = (double *)malloc(sizeof(double) * max_frames);
    double *strengths = (double *)malloc(sizeof(double) * max_frames);
    int *beat_flags = (int *)malloc(sizeof(int) * max_frames);
    if (!energies || !onsets || !strengths || !beat_flags) {
        free(energies);
        free(onsets);
        free(strengths);
        free(beat_flags);
        return 0;
    }

    size_t energy_count = 0;
    for (size_t start = 0; start < audio->mono_sample_count && energy_count < max_frames;
         start += (size_t)hop_samples) {
        size_t end = start + (size_t)window_samples;
        if (end > audio->mono_sample_count) {
            end = audio->mono_sample_count;
        }
        if (end <= start) {
            break;
        }
        energies[energy_count++] =
            rms_energy_window(audio->mono_samples + start, end - start);
    }
    if (energy_count == 0) {
        free(energies);
        free(onsets);
        free(strengths);
        free(beat_flags);
        return 0;
    }

    onsets[0] = 0.0;
    for (size_t i = 1; i < energy_count; i++) {
        double diff = energies[i] - energies[i - 1];
        onsets[i] = diff > 0.0 ? diff : 0.0;
    }

    double max_onset = 0.0;
    for (size_t i = 0; i < energy_count; i++) {
        if (onsets[i] > max_onset) {
            max_onset = onsets[i];
        }
    }
    if (max_onset <= 0.0) {
        for (size_t i = 0; i < energy_count; i++) {
            strengths[i] = 0.0;
        }
    } else {
        for (size_t i = 0; i < energy_count; i++) {
            double v = onsets[i] / max_onset;
            strengths[i] = v > 1.0 ? 1.0 : (v < 0.0 ? 0.0 : v);
        }
    }

    double fps = 1000.0 / (double)hop_ms;
    double bpm = 0.0;
    int best_lag = 0;
    if (energy_count >= 8 && fps > 0.0) {
        double min_bpm = 60.0;
        double max_bpm = 180.0;
        int lag_min = (int)llround((60.0 * fps) / max_bpm);
        int lag_max = (int)llround((60.0 * fps) / min_bpm);
        if (lag_min < 1) {
            lag_min = 1;
        }
        if (lag_max < lag_min + 1) {
            lag_max = lag_min + 1;
        }
        if (lag_max > (int)energy_count - 1) {
            lag_max = (int)energy_count - 1;
        }
        if (lag_max > lag_min) {
            double best_score = 0.0;
            for (int lag = lag_min; lag <= lag_max; lag++) {
                double score = 0.0;
                for (size_t i = (size_t)lag; i < energy_count; i++) {
                    score += onsets[i] * onsets[i - (size_t)lag];
                }
                if (score > best_score) {
                    best_score = score;
                    best_lag = lag;
                }
            }
            if (best_lag > 0) {
                bpm = (60.0 * fps) / (double)best_lag;
            }
        }
    }

    for (size_t i = 0; i < energy_count; i++) {
        beat_flags[i] = 0;
    }
    if (best_lag > 0) {
        double *phase_scores = (double *)calloc((size_t)best_lag, sizeof(double));
        if (!phase_scores) {
            free(energies);
            free(onsets);
            free(strengths);
            free(beat_flags);
            return 0;
        }
        double mean_strength = 0.0;
        for (size_t i = 0; i < energy_count; i++) {
            phase_scores[i % (size_t)best_lag] += strengths[i];
            mean_strength += strengths[i];
        }
        mean_strength /= (double)energy_count;
        size_t phase = 0;
        for (size_t i = 1; i < (size_t)best_lag; i++) {
            if (phase_scores[i] > phase_scores[phase]) {
                phase = i;
            }
        }
        double threshold = mean_strength * 1.35;
        if (threshold < 0.12) {
            threshold = 0.12;
        }
        for (size_t i = 0; i < energy_count; i++) {
            beat_flags[i] =
                ((i % (size_t)best_lag) == phase) && (strengths[i] >= threshold);
        }
        free(phase_scores);
    }

    BeatFrame *frames = (BeatFrame *)calloc(energy_count, sizeof(BeatFrame));
    if (!frames) {
        free(energies);
        free(onsets);
        free(strengths);
        free(beat_flags);
        return 0;
    }
    for (size_t i = 0; i < energy_count; i++) {
        int strength_u8 = (int)llround(strengths[i] * 255.0);
        if (strength_u8 < 0) {
            strength_u8 = 0;
        }
        if (strength_u8 > 255) {
            strength_u8 = 255;
        }
        frames[i].pos_ms = (int)(i * (size_t)hop_ms);
        frames[i].strength_u8 = strength_u8;
        frames[i].is_beat = beat_flags[i] ? 1 : 0;
    }

    out->duration_ms = audio->duration_ms;
    out->bpm = bpm > 0.0 ? bpm : 0.0;
    out->frame_count = energy_count;
    out->frames = frames;

    free(energies);
    free(onsets);
    free(strengths);
    free(beat_flags);
    return 1;
}

static void free_beat_result(BeatResult *result) {
    if (!result) {
        return;
    }
    free(result->frames);
    memset(result, 0, sizeof(*result));
}

static int compute_waveform_proxy(const DecodedAudio *audio, const Request *req, WaveformProxyResult *out) {
    memset(out, 0, sizeof(*out));
    if (!req->waveform_proxy_enabled) {
        return 1;
    }
    if (!audio || audio->stereo_rate <= 0 || !audio->left_samples || !audio->right_samples ||
        audio->stereo_sample_count == 0) {
        return 0;
    }
    int hop_frames =
        (int)((double)audio->stereo_rate * ((double)req->waveform_hop_ms / 1000.0));
    if (hop_frames < 1) {
        hop_frames = 1;
    }
    size_t max_possible_frames =
        (audio->stereo_sample_count + (size_t)hop_frames - 1) / (size_t)hop_frames;
    size_t frame_count = max_possible_frames;
    if (frame_count > (size_t)req->waveform_max_frames) {
        frame_count = (size_t)req->waveform_max_frames;
    }
    if (frame_count == 0) {
        return 0;
    }
    WaveformProxyFrame *frames =
        (WaveformProxyFrame *)calloc(frame_count, sizeof(WaveformProxyFrame));
    if (!frames) {
        return 0;
    }
    size_t start = 0;
    for (size_t i = 0; i < frame_count && start < audio->stereo_sample_count; i++) {
        size_t end = start + (size_t)hop_frames;
        if (end > audio->stereo_sample_count) {
            end = audio->stereo_sample_count;
        }
        float lmin = 1.0f, lmax = -1.0f, rmin = 1.0f, rmax = -1.0f;
        for (size_t j = start; j < end; j++) {
            float lv = audio->left_samples[j];
            float rv = audio->right_samples[j];
            if (lv < lmin) lmin = lv;
            if (lv > lmax) lmax = lv;
            if (rv < rmin) rmin = rv;
            if (rv > rmax) rmax = rv;
        }
        frames[i].pos_ms = (int)((start * 1000u) / (unsigned)audio->stereo_rate);
        frames[i].lmin = to_i8(lmin);
        frames[i].lmax = to_i8(lmax);
        frames[i].rmin = to_i8(rmin);
        frames[i].rmax = to_i8(rmax);
        start = end;
    }
    out->duration_ms = audio->duration_ms;
    out->frame_count = frame_count;
    out->frames = frames;
    return 1;
}

static void free_waveform_proxy_result(WaveformProxyResult *result) {
    if (!result) {
        return;
    }
    free(result->frames);
    memset(result, 0, sizeof(*result));
}

static void free_spectrum_result(SpectrumResult *result) {
    if (!result || !result->frames) {
        return;
    }
    for (size_t i = 0; i < result->frame_count; i++) {
        free(result->frames[i].bands);
    }
    free(result->frames);
    memset(result, 0, sizeof(*result));
}

/* We keep band_count in a static for response writing simplicity. */
static int g_response_band_count = 0;

static void write_full_response(const SpectrumResult *spec, const BeatResult *beat,
                                const WaveformProxyResult *waveform, double decode_ms,
                                double spectrum_ms, double beat_ms, double waveform_ms,
                                double total_ms) {
    printf("{\"schema\":\"%s\",\"helper_version\":\"%s\",\"duration_ms\":%d,", RESPONSE_SCHEMA,
           HELPER_VERSION, spec->duration_ms);
    printf("\"frames\":[");
    for (size_t i = 0; i < spec->frame_count; i++) {
        if (i) {
            putchar(',');
        }
        printf("[%d,[", spec->frames[i].pos_ms);
        for (int b = 0; b < g_response_band_count; b++) {
            if (b) {
                putchar(',');
            }
            printf("%u", (unsigned)spec->frames[i].bands[b]);
        }
        printf("]]");
    }
    printf("]");
    if (beat && beat->frames && beat->frame_count > 0) {
        printf(",\"beat\":{\"duration_ms\":%d,\"bpm\":%.3f,\"frames\":[", beat->duration_ms,
               beat->bpm);
        for (size_t i = 0; i < beat->frame_count; i++) {
            if (i) {
                putchar(',');
            }
            printf("[%d,%d,%s]", beat->frames[i].pos_ms, beat->frames[i].strength_u8,
                   beat->frames[i].is_beat ? "true" : "false");
        }
        printf("]}");
    }
    if (waveform && waveform->frames && waveform->frame_count > 0) {
        printf(",\"waveform_proxy\":{\"duration_ms\":%d,\"frames\":[", waveform->duration_ms);
        for (size_t i = 0; i < waveform->frame_count; i++) {
            if (i) {
                putchar(',');
            }
            printf("[%d,%d,%d,%d,%d]", waveform->frames[i].pos_ms, waveform->frames[i].lmin,
                   waveform->frames[i].lmax, waveform->frames[i].rmin, waveform->frames[i].rmax);
        }
        printf("]}");
    }
    printf(
        ",\"timings\":{\"decode_ms\":%.3f,\"spectrum_ms\":%.3f,\"beat_ms\":%.3f,\"waveform_proxy_ms\":%.3f,\"total_ms\":%.3f}}",
        decode_ms, spectrum_ms, beat_ms, waveform_ms, total_ms);
}

int main(void) {
    size_t input_len = 0;
    char *input = read_stdin_all(&input_len);
    if (!input || input_len == 0) {
        fprintf(stderr, "invalid json request\n");
        free(input);
        return 2;
    }

    Request req;
    if (!parse_request(input, &req)) {
        fprintf(stderr, "invalid request schema or fields\n");
        free(input);
        return 2;
    }
    free(input);

    double total_start = now_ms();
    double decode_start = total_start;
    DecodedAudio audio;
    if (!decode_audio_file(req.track_path, &audio)) {
        fprintf(stderr, "analysis failed (decode)\n");
        free_request(&req);
        return 1;
    }
    if (!resample_down_if_needed(&audio, req.mono_target_rate_hz)) {
        fprintf(stderr, "analysis failed (resample)\n");
        free_decoded_audio(&audio);
        free_request(&req);
        return 1;
    }
    double decode_ms = now_ms() - decode_start;

    SpectrumResult spec;
    double spectrum_start = now_ms();
    if (!compute_spectrum(&audio, &req, &spec)) {
        fprintf(stderr, "analysis failed (spectrum)\n");
        free_decoded_audio(&audio);
        free_request(&req);
        return 1;
    }
    double spectrum_ms = now_ms() - spectrum_start;
    BeatResult beat;
    double beat_ms = 0.0;
    if (req.beat_enabled) {
        double beat_start = now_ms();
        if (!compute_beat(&audio, &req, &beat)) {
            fprintf(stderr, "analysis failed (beat)\n");
            free_spectrum_result(&spec);
            free_decoded_audio(&audio);
            free_request(&req);
            return 1;
        }
        beat_ms = now_ms() - beat_start;
    } else {
        memset(&beat, 0, sizeof(beat));
    }
    WaveformProxyResult waveform;
    double waveform_ms = 0.0;
    if (req.waveform_proxy_enabled) {
        double waveform_start = now_ms();
        if (!compute_waveform_proxy(&audio, &req, &waveform)) {
            fprintf(stderr, "analysis failed (waveform_proxy)\n");
            free_beat_result(&beat);
            free_spectrum_result(&spec);
            free_decoded_audio(&audio);
            free_request(&req);
            return 1;
        }
        waveform_ms = now_ms() - waveform_start;
    } else {
        memset(&waveform, 0, sizeof(waveform));
    }
    double total_ms = now_ms() - total_start;

    g_response_band_count = req.band_count;
    write_full_response(&spec, &beat, &waveform, decode_ms, spectrum_ms, beat_ms, waveform_ms,
                        total_ms);

    free_beat_result(&beat);
    free_waveform_proxy_result(&waveform);
    free_spectrum_result(&spec);
    free_decoded_audio(&audio);
    free_request(&req);
    return 0;
}
