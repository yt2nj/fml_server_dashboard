# 启动命令示例：python fml_server_dashboard_slave.py --name DELL-G3 --master 127.0.0.1:9901
# 功能：收集本机系统信息（CPU、内存、硬盘、GPU），编码为JSON并通过UDP发送给master节点

# ---------- 导入必要的系统库和第三方库 ----------
import socket
import sys
import argparse
import time
import os
import shutil
import platform
import re
import json


# ---------- 解析命令行参数：获取节点名称和master地址 ----------
def parse_args():
    parser = argparse.ArgumentParser(description="服务器监控从节点")
    parser.add_argument("--name", required=True, help="从节点名称")
    parser.add_argument("--master", required=True, help="主节点地址，格式为 IP:端口")
    return parser.parse_args()


# ---------- 根据百分比数值返回对应的颜色代码，用于前端展示 ----------
def get_color_by_percent(percent):
    try:
        p = float(percent)
        assert p >= 0 and p <= 100
    except:
        return "#000000"
    # 绿色(低)<蓝色<橙色<红色(高)
    if p < 20:
        return "#22aa22"  # 绿
    elif p < 50:
        return "#2288ee"  # 蓝
    elif p < 80:
        return "#ee8800"  # 橙
    else:
        return "#ee2222"  # 红


# ---------- 获取本机的IP地址，通过连接外部地址来获取真实IP ----------
def get_ip_address():
    try:
        # 连接到外部DNS服务器获取本机IP，不实际发送数据
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    # 如果是本地环回地址则标记为unknown
    if ip in {"127.0.0.1", "localhost"}:
        ip = "unknown"
    return ip


# ---------- 获取CPU温度 ----------
def get_cpu_temp():
    try:
        if shutil.which("/sys/class/thermal/thermal_zone0/temp") is None:
            return "无法获取温度"
        if platform.system() == "Linux":
            with open("/sys/class/thermal/thermal_zone0/temp") as f:
                milli = int(f.read().strip())
            temp = milli / 1000.0  # 摄氏度
            color = get_color_by_percent(min(temp, 100))  # 把温度直接当百分比用
            return f'温度 <span style="color:{color}">{temp:.1f}°C</span>'
        else:
            return "无法获取温度"
    except Exception as e:
        print(f"获取温度失败: {e}")
        return "出错"


# ---------- 获取CPU使用率，通过读取/proc/stat文件计算（仅限Linux系统） ----------
def get_cpu_usage():
    try:
        if platform.system() == "Linux":
            # 第一次读取CPU状态
            with open("/proc/stat", "r") as f:
                line = f.readline().split()
                total = sum(int(x) for x in line[1:])
                idle = int(line[4])
            # 等待1秒后再次读取，计算两次之间的差值
            time.sleep(1)
            with open("/proc/stat", "r") as f:
                line = f.readline().split()
                total2 = sum(int(x) for x in line[1:])
                idle2 = int(line[4])
            # 计算CPU使用率并添加颜色标记
            usage = (1 - (idle2 - idle) / (total2 - total)) * 100
            color = get_color_by_percent(usage)
            return f'CPU <span style="color:{color}">{usage:.2f}%</span>'
        else:
            return "无法获取 CPU 使用率"
    except Exception as e:
        print(f"获取 CPU 使用率失败: {e}")
        return "出错"


# ---------- 获取内存信息，包括物理内存和Swap的使用情况及百分比 ----------
def get_memory_info():
    try:
        if platform.system() == "Linux":
            # 读取内存信息文件，解析各项数据
            with open("/proc/meminfo", "r") as f:
                lines = f.readlines()
                total_kb = int(re.search(r"MemTotal:\s+(\d+)", lines[0]).group(1))
                available_kb = int(re.search(r"MemAvailable:\s+(\d+)", lines[2]).group(1))
                swap_total_kb = int(re.search(r"SwapTotal:\s+(\d+)", lines[14]).group(1))
                swap_free_kb = int(re.search(r"SwapFree:\s+(\d+)", lines[15]).group(1))
            # 转换为GB单位并计算使用率
            total = total_kb / 1024 / 1024
            available = available_kb / 1024 / 1024
            used = total - available
            mem_percent = (used / total * 100) if total > 0 else 0
            # 计算Swap使用情况
            swap_total = swap_total_kb / 1024 / 1024
            swap_free = swap_free_kb / 1024 / 1024
            swap_used = swap_total - swap_free
            swap_percent = (swap_used / swap_total * 100) if swap_total > 0 else 0
            # 生成带颜色的显示字符串
            mem_color = get_color_by_percent(mem_percent)
            swap_color = get_color_by_percent(swap_percent)
            return {
                "memory_detail": {
                    "total": round(total, 2),
                    "used": round(used, 2),
                    "percent": f"{mem_percent:.2f}%",
                    "swap_total": round(swap_total, 2),
                    "swap_used": round(swap_used, 2),
                    "swap_percent": f"{swap_percent:.2f}%",
                },
                "display": f'内存 {used:.2f}GB/{total:.2f}GB=<span style="color:{mem_color}">{mem_percent:.2f}%</span><br>Swap {swap_used:.2f}GB/{swap_total:.2f}GB=<span style="color:{swap_color}">{swap_percent:.2f}%</span>',
            }
        else:
            return {"display": "无法获取"}
    except Exception as e:
        print(f"获取内存信息失败: {e}")
        return {"display": "出错"}


# ---------- 获取根目录的硬盘使用情况信息 ----------
def get_disk_info():
    try:
        if platform.system() == "Linux":
            disk_detail = []
            display_list = []
            for line in os.popen("df -kP | awk 'NR>1 {print $6}' | sort -u").read().splitlines():
                mount = line.strip()
                stat = os.statvfs(mount)
                total = (stat.f_blocks * stat.f_frsize) // (1024**3)
                free = (stat.f_bfree * stat.f_frsize) // (1024**3)
                used = total - free
                if total < 256:
                    continue  # 忽略小于256GB的挂载点
                percent = (used / total * 100) if total > 0 else 0
                color = get_color_by_percent(percent)
                disk_detail.append(
                    {
                        "mount": mount,
                        "total": total,
                        "used": used,
                        "percent": f"{percent:.2f}%",
                    }
                )
                display_list.append(f'{mount} {used}GB/{total}GB=<span style="color:{color}">{percent:.2f}%</span>')
            return {"disk_detail": disk_detail, "display": "<br>".join(display_list)} if disk_detail else {"display": "无硬盘"}
        else:
            return {"display": "无法获取"}
    except Exception as e:
        print(f"获取硬盘信息失败: {e}")
        return {"display": "出错"}


# ---------- 获取GPU信息，需要nvidia-smi命令支持 ----------
def get_gpu_info():
    # 辅助函数：重新格式化GPU信息，提取数值部分
    def reformat_gpu_info(util, mem_used, mem_total, fan, power):
        import re

        digits = re.compile(r"[.0-9]+")

        def extract_first_match(text):
            match = digits.findall(text)
            return match[0] if match else "N/A"

        # 从nvidia-smi输出中提取纯数字部分
        util_val = extract_first_match(util)
        mem_used_val = extract_first_match(mem_used)
        mem_total_val = extract_first_match(mem_total)
        fan_val = extract_first_match(fan)
        power_val = extract_first_match(power)
        return util_val, mem_used_val, mem_total_val, fan_val, power_val

    try:
        import subprocess

        if shutil.which("nvidia-smi") is None:
            return {"display": "无GPU"}

        # 执行nvidia-smi命令获取GPU信息
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=utilization.gpu,memory.used,memory.total,fan.speed,power.draw", "--format=csv"],
            capture_output=True,
            text=True,
        )
        # 解析输出，跳过标题行
        lines = result.stdout.splitlines()[1:]
        gpu_detail = []
        display_list = []
        # 处理每个GPU的信息
        for i, line in enumerate(lines):
            util, mem_used, mem_total, fan, power = line.split(", ")
            util, mem_used, mem_total, fan, power = reformat_gpu_info(util, mem_used, mem_total, fan, power)
            # 计算显存使用率
            try:
                mem_ratio = float(mem_used) / float(mem_total) * 100
            except:
                mem_ratio = 0
            # 生成带颜色的显示信息
            util_color = get_color_by_percent(util)
            mem_color = get_color_by_percent(mem_ratio)
            gpu_detail.append(
                {
                    "index": i,
                    "util": f'<span style="color:{util_color}">{util}%</span>',
                    "memory": f'<span style="color:{mem_color}">{mem_used}MB/{mem_total}MB={mem_ratio:.2f}%</span>',
                    "fan": f"{fan}%",
                    "power": f"{power}W",
                }
            )
            display_list.append(
                f'[GPU{i}]<br>使用 <span style="color:{util_color}">{util}%</span> 风扇 {fan}% 功率 {power}W<br>显存 <span style="color:{mem_color}">{mem_used}MB/{mem_total}MB={mem_ratio:.2f}%</span>'
            )
        return {"gpu_detail": gpu_detail, "display": "<br>".join(display_list)} if gpu_detail else {"display": "无GPU"}
    except Exception as e:
        print(f"获取 GPU 信息失败: {e}")
        return {"display": "出错"}


# ---------- 主程序入口：解析参数、收集系统信息、发送数据到master节点 ----------
def main():
    # 解析命令行参数获取节点名称和master地址
    args = parse_args()
    name = args.name
    master_host, master_port = args.master.split(":")
    master_port = int(master_port)

    # 创建UDP套接字用于发送数据
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    # 主循环：持续收集和发送系统信息
    while True:
        # 收集各项系统信息并组装成字典
        info = {
            "name": {"display": name},
            "ip": {"display": get_ip_address()},
            "cpu": {"display": "<br>".join([get_cpu_usage(), get_cpu_temp()])},
            "memory": get_memory_info(),
            "disk": get_disk_info(),
            "gpu": get_gpu_info(),
            "timestamp": {"display": time.strftime("%Y-%m-%d %H:%M:%S")},
        }
        # 将字典编码为JSON格式的UTF-8二进制数据
        try:
            message = json.dumps(info, ensure_ascii=False).encode("utf-8")
        except Exception as e:
            print(f"JSON 编码失败: {e}")
            continue

        # 通过UDP发送数据到master节点
        try:
            sock.sendto(message, (master_host, master_port))
            print(f"已发送数据到 {master_host}:{master_port}")
        except Exception as e:
            print(f"发送失败: {e}")

        # 每120秒发送一次数据
        time.sleep(120)


if __name__ == "__main__":
    main()
