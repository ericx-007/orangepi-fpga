# 实测硬件配置

记录日期：2026-10-23。以下为这套设备的实测和官方工程选型，不是所有 Orange Pi 型号的通用配置。

| 项目 | 配置 |
|---|---|
| 主板设备树名称 | Orange Pi Ai Pro |
| 芯片平台标识 | `hisilicon,hi1910B-evb` / `hisilicon,ascend610` |
| CPU | 4 核 ARM 64 位，aarch64 |
| 内存 | 16 GB 档，Linux 显示约 15 GiB |
| 存储 | 64 GB SD 卡，实际 59.5 GiB；ext4 根分区约 58 GiB |
| 系统 | openEuler 22.03 LTS-SP4 |
| 内核 | Linux 5.10.0+ |
| NPU | Ascend 310B4，驱动 23.0.0 |
| FPGA 扩展板 | OPi MSOC，带 MicroUSB 接口版本 |
| 官方工程器件选型 | GW5AT-138B，GW5AT-LV138PG484AC1/I0，PBGA484A |
| JTAG 器件码 | `0x0011081B` |
| FPGA 时钟 | 25 MHz，V18 |
| 外设 | 两组 4 位数码管、16 个 LED、4 个用户按键、两排各 8 位拨码开关 |
| PCIe 枚举 | `22c2:1100`，实测 Gen2 ×4；本项目未使用 PCIe 数据通路 |
| USB 调试 | FTDI FT2232，通道 A 为 JTAG，通道 B 为 UART |

初次检查时 NPU 状态为 Alarm，原因未在本项目中排查。本演示使用 CPU、FPGA 和 UART，不依赖 NPU、CANN 或 MindIE。PCIe 链路存在不代表已经安装 FPGA PCIe 驱动。

## 引脚与电平

引脚来源是厂商提供的《OrangePi MSOC 带 MicroUSB 接口版本用户手册 v1.0》第 4–5 页及配套源码。表格已与 PDF 画面和官方 `.cst` 核对。完整映射见 [`panel.cst`](../rtl/panel.cst)。

| 信号 | FPGA 引脚 |
|---|---|
| 时钟 | V18 |
| UART RX / TX | Y19 / U20 |
| K1–K4 | V20 / W19 / W20 / W21 |
| 段 A–G、DP | M21 / L21 / M17 / J22 / H22 / K21 / K22 / J20 |
| 第一组 4 位选择 | K17 / J17 / L14 / L15 |
| 第二组 4 位选择 | L16 / M16 / H20 / G20 |

使用 LVCMOS33。数码管段选低有效、位选高有效，每组位选在实体上从右向左排列；RTL 已转换为用户输入的从左向右顺序。按键低有效，协议转换成 1 表示按下。拨码 ON 为 1。

网页第一排显示协议拨码值的高 8 位，第二排显示低 8 位，以匹配此实物的上下布局。每排编号 1 对应该排的最低位。不同板卡布局请先核对，调整网页映射无需改 FPGA 协议。

## 教育版器件名和配置流

这套板的旧标准版工具使用 GW5AT-138B 名称。免费 V1.9.11.03 Education 提供的目标名为 GW5AST-138B。旧工具这两个目标的 `.fse` 和 `.csr` 文件分别具有相同 SHA256：

```text
fse: 2ff142ef3522d0444fa6bdc04980d0f397fbe1bad8584e86879c7a6a17d20229
csr: 078ec582d38af28cf00e04b4772dc809090d6feba4119805ca7eac29a3cea280
```

这提供了配置数据库兼容的证据。它们的 `.dat` 和时序文件不完全相同，因此这里不声称两款器件的全部特性相同。

新工具生成配置头的期望 ID 为 `0001081B`，本板实测为 `0011081B`。直接下载会报 ID 校验错误。`tools/adapt_bitstream.py` 验证原始全部 21872 帧 CRC，再仅调整期望 ID 及受影响的首帧 CRC，保持逻辑配置帧载荷不变。CRC 帧规则参考 [Apicula](https://github.com/YosysHQ/apicula)。

适配后的这套设计已通过实体板测试。Gowin 状态寄存器的 bit 13 是 DONE，bit 0–3 分别是 CRC、命令、ID 和超时错误，定义见 [厂商状态寄存器说明](https://cdn.gowinsemi.com.cn/TN711E.pdf)。不要把这项适配推广到未核对的硬件。

资料入口：[OPi MSOC 官方支持页](http://www.orangepi.cn/html/hardWare/computerAndMicrocontrollers/service-and-support/Orange-pi-MSOC.html)、[Gowin 教育版下载](https://www.gowinsemi.com/en/support/database/1865/)。
