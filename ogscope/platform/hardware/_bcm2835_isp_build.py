"""bcm2835-isp 内核头文件绑定（cffi API 模式）/ bcm2835-isp kernel header bindings (cffi API mode).

结构体布局、ioctl 编号和控件 ID 全部由 C 编译器从内核 uapi 头文件
（linux/videodev2.h、linux/bcm2835-isp.h）取得，Python 侧不再手写任何 ABI 数值；
头文件与布局不一致时编译直接失败，而不是在设备上传错数据。
Struct layouts, ioctl numbers and control IDs all come from the C compiler
reading the kernel uapi headers (linux/videodev2.h, linux/bcm2835-isp.h): no
ABI number is hand-written on the Python side, and a header/layout mismatch
fails the build instead of passing wrong data on the device.

bcm2835-isp.h 只存在于树莓派内核，主线 linux-libc-headers 中没有，因此
OGSCOPE_KERNEL_HEADERS 指向对运行内核执行 ``make headers_install`` 得到的
include 目录（Yocto 配方负责生成）。开发机上手动构建：
bcm2835-isp.h exists only in the Raspberry Pi kernel, not in mainline
linux-libc-headers, so OGSCOPE_KERNEL_HEADERS points at the include directory
``make headers_install`` produces for the running kernel (the Yocto recipe
generates it). To build by hand on a development host:

    make -C rpi-linux O=/tmp/khdr/build headers_install INSTALL_HDR_PATH=/tmp/khdr
    OGSCOPE_KERNEL_HEADERS=/tmp/khdr/include python ogscope/platform/hardware/_bcm2835_isp_build.py
"""

from __future__ import annotations

import os

from cffi import FFI

MODULE = "ogscope.platform.hardware._bcm2835_isp_cffi"

# 带 "..." 的结构体只声明用到的字段，偏移与大小由编译器给出；
# ISP 控件结构体完整声明，cffi 在编译期逐字段核对。
# Structs ending in "..." declare only the fields used, offsets and sizes
# come from the compiler; ISP control structs are declared in full and cffi
# checks every field against the header at compile time.
CDEF = """
#define VIDIOC_S_FMT ...
#define VIDIOC_REQBUFS ...
#define VIDIOC_QUERYBUF ...
#define VIDIOC_QBUF ...
#define VIDIOC_DQBUF ...
#define VIDIOC_STREAMON ...
#define VIDIOC_STREAMOFF ...
#define VIDIOC_S_EXT_CTRLS ...

#define V4L2_PIX_FMT_SRGGB16 ...
#define V4L2_PIX_FMT_SBGGR16 ...
#define V4L2_PIX_FMT_SGRBG16 ...
#define V4L2_PIX_FMT_SGBRG16 ...
#define V4L2_PIX_FMT_RGB24 ...

#define V4L2_CID_RED_BALANCE ...
#define V4L2_CID_BLUE_BALANCE ...
#define V4L2_CID_DIGITAL_GAIN ...
#define V4L2_CID_USER_BCM2835_ISP_CC_MATRIX ...
#define V4L2_CID_USER_BCM2835_ISP_BLACK_LEVEL ...
#define V4L2_CID_USER_BCM2835_ISP_GAMMA ...
#define V4L2_CID_USER_BCM2835_ISP_DENOISE ...
#define V4L2_CID_USER_BCM2835_ISP_SHARPEN ...
#define V4L2_CID_USER_BCM2835_ISP_DPC ...
#define V4L2_CID_USER_BCM2835_ISP_CDN ...
#define BCM2835_NUM_GAMMA_PTS ...

static const int V4L2_BUF_TYPE_VIDEO_CAPTURE;
static const int V4L2_BUF_TYPE_VIDEO_OUTPUT;
static const int V4L2_MEMORY_MMAP;
static const int V4L2_FIELD_NONE;
static const int V4L2_COLORSPACE_SRGB;
static const int V4L2_COLORSPACE_RAW;

struct v4l2_pix_format {
    uint32_t width;
    uint32_t height;
    uint32_t pixelformat;
    uint32_t field;
    uint32_t bytesperline;
    uint32_t sizeimage;
    uint32_t colorspace;
    ...;
};
struct v4l2_format { uint32_t type; ...; };
struct v4l2_requestbuffers { uint32_t count; uint32_t type; uint32_t memory; ...; };
struct v4l2_buffer {
    uint32_t index;
    uint32_t type;
    uint32_t bytesused;
    uint32_t field;
    uint32_t memory;
    uint32_t length;
    ...;
};
struct v4l2_ext_control { uint32_t id; uint32_t size; ...; };
struct v4l2_ext_controls { uint32_t count; struct v4l2_ext_control *controls; ...; };

struct bcm2835_isp_rational { int32_t num; uint32_t den; };
struct bcm2835_isp_ccm { struct bcm2835_isp_rational ccm[3][3]; int32_t offsets[3]; };
struct bcm2835_isp_custom_ccm { uint32_t enabled; struct bcm2835_isp_ccm ccm; };
struct bcm2835_isp_black_level {
    uint32_t enabled;
    uint16_t black_level_r;
    uint16_t black_level_g;
    uint16_t black_level_b;
    uint8_t padding[2];
};
struct bcm2835_isp_gamma { uint32_t enabled; uint16_t x[33]; uint16_t y[33]; };
struct bcm2835_isp_denoise {
    uint32_t enabled;
    uint32_t constant;
    struct bcm2835_isp_rational slope;
    struct bcm2835_isp_rational strength;
};
struct bcm2835_isp_sharpen {
    uint32_t enabled;
    struct bcm2835_isp_rational threshold;
    struct bcm2835_isp_rational strength;
    struct bcm2835_isp_rational limit;
};
struct bcm2835_isp_dpc { uint32_t enabled; uint32_t strength; };
struct bcm2835_isp_cdn { uint32_t enabled; uint32_t mode; };

/* 匿名/具名联合体成员的访问器 / Accessors for union members */
struct v4l2_pix_format *ogscope_format_pix(struct v4l2_format *format);
uint32_t ogscope_buffer_offset(const struct v4l2_buffer *buffer);
void ogscope_control_set_value(struct v4l2_ext_control *control, int32_t value);
void ogscope_control_set_ptr(struct v4l2_ext_control *control, void *ptr);

int ioctl(int fd, unsigned long request, ...);
"""

SOURCE = """
#include <sys/ioctl.h>
#include <linux/videodev2.h>
#include <linux/bcm2835-isp.h>

_Static_assert(BCM2835_NUM_GAMMA_PTS == 33, "bcm2835_isp_gamma has 33 points");

static struct v4l2_pix_format *ogscope_format_pix(struct v4l2_format *format)
{
    return &format->fmt.pix;
}

static uint32_t ogscope_buffer_offset(const struct v4l2_buffer *buffer)
{
    return buffer->m.offset;
}

static void ogscope_control_set_value(struct v4l2_ext_control *control, int32_t value)
{
    control->value = value;
}

static void ogscope_control_set_ptr(struct v4l2_ext_control *control, void *ptr)
{
    control->ptr = ptr;
}
"""

ffibuilder = FFI()
ffibuilder.cdef(CDEF)
_headers = os.environ.get("OGSCOPE_KERNEL_HEADERS")
ffibuilder.set_source(MODULE, SOURCE, include_dirs=[_headers] if _headers else [])


if __name__ == "__main__":
    # 在仓库根目录下原地生成扩展模块 / Build the extension in place under the repository root.
    ffibuilder.compile(
        tmpdir=os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."
        ),
        verbose=True,
    )
