# 编译、部署与恢复

## 准备

本指南对应 [已验证的硬件](hardware.md)。电脑可为 Windows；板端需要 Linux、Python 3、systemd、`timeout`、`modprobe` 及已经安装的 Gowin Programmer。板端下载器路径为 `/opt/Gowin/Programmer/bin/programmer_cli`。其他路径需要修改 `tools/program-sram.sh`。

从 [Gowin 官方网站](https://www.gowinsemi.com/en/support/database/1865/) 安装 V1.9.11.03 Education。本项目在 Windows x64 教育版完成编译，无需原标准版的许可证。确认器件列表包含 GW5AST-138B 和 PG484A 封装。

在仓库根目录安装电脑端 SSH 部署依赖：

```sh
python -m pip install -r requirements.txt
```

板端服务只用 Python 标准库，无需安装 Paramiko。

## 编译 FPGA

```sh
cd rtl
gw_sh education-check.tcl
cd ..
python tools/adapt_bitstream.py
```

如果 `gw_sh` 不在 PATH，使用安装目录中 `IDE/bin/gw_sh.exe` 的完整路径。构建输出在 `rtl/impl/pnr/panel.fs`；适配输出为 `panel-board-id.fs`。适配脚本会验证原始每帧 CRC，失败时不会继续。生成的审计记录在 `build/bitstream-adaptation.json`。

适配仅适用于本项目实测的 B 版硬件。先用 Gowin Programmer 的只读扫描核对 JTAG ID，不要向 C 版或其他器件下载本配置。原工程、脚本和厂商安装包均不需要上传到 GitHub。

## 部署到主板

先用原生 SSH 核对主机指纹，并接受你确认正确的主机密钥，然后退出连接：

```sh
ssh root@BOARD_IP
```

电脑端部署工具使用已有 `~/.ssh/known_hosts`，拒绝未知或变化的主机密钥。替换 `BOARD_IP` 后运行：

```sh
python tools/deploy.py --host BOARD_IP --bitstream rtl/impl/pnr/panel-board-id.fs
```

密码在终端中隐藏输入，不保存在仓库或配置文件。部署需要 root，因为涉及设备下载和 systemd 单元安装。工具只操作 `/opt/fpga-panel`、对应服务单元及 FPGA SRAM。

部署会停止现有 `fpga-panel` 服务，上传网页、服务和配置流，加载 SRAM，恢复 FTDI 串口驱动，再启动服务。显示值与按键计数会复位。下载脚本以 DONE 和错误位判断成功，因为实测旧版下载器即使成功仍可能返回非零进程码。网页的 FPGA 应答仍是独立的功能检查。

## 打开网页

在电脑终端保持下面命令运行：

```sh
ssh -N -L 127.0.0.1:8088:127.0.0.1:8088 root@BOARD_IP
```

打开 <http://127.0.0.1:8088>，等到“FPGA 已连接”，再输入 `01234567`。两组实体数码管应为 `0123 / 4567`。依次按 K1–K4，网页对应按键会亮起，事件计数增加。拨动各个拨码开关，核对网页相同位置的 ON/OFF。

第一排拨码对应协议高字节，第二排对应低字节，已按实物上下位置调整。拨码状态只用于显示，不会覆盖网页写入的数字。

## 断电与故障恢复

本项目只加载 SRAM，不擦写 Flash，没有开机自动下载。断电后 FPGA 恢复原 Flash 程序；重新运行部署命令，再建立 SSH 隧道即可。

板端常用检查：

```sh
systemctl status fpga-panel --no-pager
journalctl -u fpga-panel -n 40 --no-pager
ls -l /dev/serial/by-id/
curl http://127.0.0.1:8088/api/state
```

默认串口是 `/dev/serial/by-id/usb-FTDI_Dual_RS232-HS-if01-port0`。如果系统生成的名称不同，可修改 systemd 的 `ExecStart`，追加 `--port /dev/实际串口`。编程器操作会卸载 FTDI 驱动；脚本通过退出处理恢复 `ftdi_sio`。

“服务已运行”与“FPGA 已连接”不同。如果服务正常但硬件离线，检查 FPGA 是否因断电恢复旧程序、串口是否选对、下载状态是否成功。不要打开默认 JTAG 通道并向其中发送串口命令。

回到原 FPGA 程序可关闭服务后给扩展板重新上电。服务器故障不会改动 Flash 中的原程序。要删除本项目服务，先停用并删除 `/etc/systemd/system/fpga-panel.service`，再运行 `systemctl daemon-reload`。
