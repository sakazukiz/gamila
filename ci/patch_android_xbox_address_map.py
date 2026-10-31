#!/usr/bin/env python3
"""Reserve the Android Xbox contiguous arena and test the kernel PE probe."""
from pathlib import Path
import sys


def replace_once(source: str, anchor: str, replacement: str, marker: str, label: str) -> str:
    if marker in source:
        return source
    count = source.count(anchor)
    if count != 1:
        detail = ""
        if label == "release reserved contiguous slot":
            lo = source.find("Contiguous / physical memory window")
            hi = source.find("NV2A hardware register aperture", lo + 1)
            if lo >= 0 and hi > lo:
                detail = "\\n--- actual contiguous mapping source ---\\n" + source[lo:hi]
        raise SystemExit(f"{label}: expected one anchor, found {count}{detail}")
    return source.replace(anchor, replacement, 1)


def patch_layout(path: Path) -> None:
    s = path.read_text()
    s = replace_once(s, "#include <stdio.h>\n",
        "#include <stdio.h>\n#if defined(__ANDROID__)\n#include <android/log.h>\n"
        '#define NFSU2_MEM_LOG(...) __android_log_print(ANDROID_LOG_ERROR, "NFSU2-MEM", __VA_ARGS__)\n'
        "#else\n#define NFSU2_MEM_LOG(...) ((void)0)\n#endif\n",
        "#define NFSU2_MEM_LOG", "Android log include")
    s = replace_once(s,
        "        g_span_size = g_memory_size * (size_t)(1 + XBOX_NUM_MIRRORS);\n",
        "        g_span_size = g_memory_size * (size_t)(1 + XBOX_NUM_MIRRORS);\n"
        "#if defined(__ANDROID__)\n"
        "        /* Reserve the full guest range up to the contiguous arena.\n"
        "         * The old RAM/mirror-only reservation left 0x80000000 in an\n"
        "         * unreserved gap that Android mmap ASLR could occupy. */\n"
        "        {\n"
        "            const size_t end = (size_t)XBOX_CONTIG_BASE + XBOX_CONTIG_SIZE - XBOX_MAP_START;\n"
        "            if (g_span_size < end) g_span_size = end;\n"
        "        }\n"
        "#endif\n",
        "const size_t end", "Android full-span reservation")
    s = replace_once(s,
        "        uintptr_t contig_native = XBOX_CONTIG_BASE + g_memory_offset;\n",
        "        uintptr_t contig_native = XBOX_CONTIG_BASE + g_memory_offset;\n"
        "#if defined(__ANDROID__)\n"
        "        /* Release the reserved 64 MiB slice before installing its shared mapping. */\n"
        "        if (g_span_base && !VirtualFree((LPVOID)contig_native, XBOX_CONTIG_SIZE, MEM_RELEASE)) {\n"
        '            fprintf(stderr, "[FATAL] cannot release reserved contiguous VA 0x%08X (error %lu)\\n", XBOX_CONTIG_BASE, GetLastError());\n'
        '            NFSU2_MEM_LOG("FATAL: cannot release contiguous VA guest=0x%08X host=%p error=%lu", XBOX_CONTIG_BASE, (void *)contig_native, GetLastError());\n'
        "            return FALSE;\n"
        "        }\n"
        "#endif\n"
        "        g_contig_mapping = CreateFileMappingW(\n",
        "cannot release reserved contiguous VA", "release reserved contiguous slot")
    s = replace_once(s,
        "        uint64_t tiled_lo = XBOX_TILED_BASE;\n"
        "        uint64_t tiled_hi = tiled_lo + xbox_TiledApertureSize();\n\n"
        "        for (int m = 0; m < XBOX_NUM_MIRRORS; m++) {\n",
        "        uint64_t tiled_lo = XBOX_TILED_BASE;\n"
        "        uint64_t tiled_hi = tiled_lo + xbox_TiledApertureSize();\n"
        "        uint64_t contig_lo = XBOX_CONTIG_BASE;\n"
        "        uint64_t contig_hi = contig_lo + XBOX_CONTIG_SIZE;\n\n"
        "        for (int m = 0; m < XBOX_NUM_MIRRORS; m++) {\n",
        "uint64_t contig_lo = XBOX_CONTIG_BASE", "contiguous bounds")
    s = replace_once(s,
        '            if (guest_lo < tiled_hi && tiled_lo < guest_hi) {\n'
        '                fprintf(stderr, "  Mirror %d: skipped, overlaps the tiled"\n'
        '                                " aperture at 0x%08X\\n",\n'
        "                        m + 1, (unsigned)XBOX_TILED_BASE);\n"
        "                continue;\n"
        "            }\n",
        '            if (guest_lo < tiled_hi && tiled_lo < guest_hi) {\n'
        '                fprintf(stderr, "  Mirror %d: skipped, overlaps the tiled"\n'
        '                                " aperture at 0x%08X\\n",\n'
        "                        m + 1, (unsigned)XBOX_TILED_BASE);\n"
        "                continue;\n"
        "            }\n"
        "            /* The contiguous arena is separate storage, not a RAM mirror. */\n"
        "            if (guest_lo < contig_hi && contig_lo < guest_hi) {\n"
        '                fprintf(stderr, "  Mirror %d: skipped, overlaps the contiguous arena at 0x%08X\\n",\n'
        "                        m + 1, (unsigned)XBOX_CONTIG_BASE);\n"
        "                continue;\n"
        "            }\n",
        "overlaps the contiguous arena", "skip contiguous mirror overlap")
    s = replace_once(s,
        '        } else {\n'
        '            fprintf(stderr, "  WARNING: could not map Xbox kernel VA 0x%08X\\n",\n'
        "                    XBOX_KERNEL_BASE);\n"
        "        }\n"
        "        #undef XBOX_KERNEL_BASE\n",
        '        } else {\n'
        '            fprintf(stderr, "  WARNING: could not map Xbox kernel VA 0x%08X\\n",\n'
        "                    XBOX_KERNEL_BASE);\n"
        "        }\n"
        "#if defined(__ANDROID__)\n"
        "        /* RenderWare's first cache probe reads MEM32(0x8001003C). */\n"
        "        if (!g_contig_memory || !g_kernel_memory || (uintptr_t)g_kernel_memory != kernel_native) {\n"
        '            fprintf(stderr, "[FATAL] Xbox contiguous/kernel VA unavailable: contiguous=%p kernel=%p expected=%p\\n", g_contig_memory, g_kernel_memory, (void *)kernel_native);\n'
        '            NFSU2_MEM_LOG("FATAL: Xbox VA mapping invalid contiguous=%p kernel=%p expected=%p offset=%p", g_contig_memory, g_kernel_memory, (void *)kernel_native, (void *)(uintptr_t)g_memory_offset);\n'
        "            return FALSE;\n"
        "        }\n"
        "        {\n"
        "            volatile uint32_t *pe_lfanew = (volatile uint32_t *)(kernel_native + 0x3Cu);\n"
        "            uint32_t value = *pe_lfanew;\n"
        "            if (value != 0x80u) {\n"
        '                fprintf(stderr, "[FATAL] kernel PE probe [0x8001003C]=0x%08X\\n", value);\n'
        '                NFSU2_MEM_LOG("FATAL: kernel PE probe guest=0x8001003C host=%p value=0x%08X", (void *)(kernel_native + 0x3Cu), value);\n'
        "                return FALSE;\n"
        "            }\n"
        '            NFSU2_MEM_LOG("Xbox VA verified: base=%p offset=%p span=%zu contig=%p kernel=%p PE[0x8001003C]=0x%08X", g_memory_base, (void *)(uintptr_t)g_memory_offset, g_span_size, g_contig_memory, g_kernel_memory, value);\n'
        "        }\n"
        "#endif\n"
        "        #undef XBOX_KERNEL_BASE\n",
        "Xbox contiguous/kernel VA unavailable", "fail-fast kernel page validation")
    path.write_text(s)


def patch_test(path: Path) -> None:
    s = path.read_text()
    s = replace_once(s,
        '    check(size > 0, "mapped size is non-zero", NULL);\n',
        '    check(size > 0, "mapped size is non-zero", NULL);\n'
        "    {\n"
        "        volatile uint32_t *pe_lfanew = (volatile uint32_t *)((uintptr_t)base + 0x8001003Cu);\n"
        "        uint32_t value = *pe_lfanew;\n"
        '        check(value == 0x80u, "Xbox kernel PE header at guest 0x8001003C",\n'
        '              "contiguous arena must be mapped before guest startup");\n'
        "    }\n",
        "Xbox kernel PE header at guest 0x8001003C", "kernel PE regression")
    path.write_text(s)


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: patch_android_xbox_address_map.py PROJECT_DIR")
    root = Path(sys.argv[1])
    patch_layout(root / "xboxrecomp/src/kernel/xbox_memory_layout.c")
    patch_test(root / "xboxrecomp/tests/memory_layout_posix/test_main.c")
    print("Android Xbox VA span and 0x8001003C regression patch applied")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
