# python fml_server_dashboard_slave.py --name DELL-G3 --master 127.0.0.1:9901
# 功能：收集本机系统信息，编码为 JSON 并通过 UDP 发送给 master

import socket
import sys
import argparse
import time
import os
import platform
import re
import json


# 解析命令行参数
def parse_args():
    parser = argparse.ArgumentParser(description="服务器监控从节点")
    parser.add_argument("--name", required=True, help="从节点名称")
    parser.add_argument("--master", required=True, help="主节点地址，格式为 IP:端口")
    return parser.parse_args()


def get_color_by_percent(percent):
    try:
        p = float(percent)
    except:
        return "#000000"
    if p < 20:
        return "#22aa22"  # 绿
    elif p < 50:
        return "#2288ee"  # 蓝
    elif p < 80:
        return "#ee8800"  # 橙
    else:
        return "#ee2222"  # 红


# 获取自身 IP 地址
def get_ip_address():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    if ip in {"127.0.0.1", "localhost"}:
        ip = "unknown"
    return ip


# 获取 CPU 使用率（兼容 Linux 和部分非 Linux 系统）
def get_cpu_usage():
    try:
        if platform.system() == "Linux":
            with open("/proc/stat", "r") as f:
                line = f.readline().split()
                total = sum(int(x) for x in line[1:])
                idle = int(line[4])
            time.sleep(1)  # 等待1秒以计算差值
            with open("/proc/stat", "r") as f:
                line = f.readline().split()
                total2 = sum(int(x) for x in line[1:])
                idle2 = int(line[4])
            usage = (1 - (idle2 - idle) / (total2 - total)) * 100
            color = get_color_by_percent(usage)
            return f'CPU <span style="color:{color}">{usage:.2f}%</span>'
        else:
            return "无法获取"
    except Exception as e:
        print(f"获取 CPU 使用率失败: {e}")
        return "出错"


# 获取内存信息（包含百分比）
def get_memory_info():
    try:
        if platform.system() == "Linux":
            with open("/proc/meminfo", "r") as f:
                lines = f.readlines()
                total_kb = int(re.search(r"MemTotal:\s+(\d+)", lines[0]).group(1))
                free_kb = int(re.search(r"MemFree:\s+(\d+)", lines[1]).group(1))
                swap_total_kb = int(re.search(r"SwapTotal:\s+(\d+)", lines[14]).group(1))
                swap_free_kb = int(re.search(r"SwapFree:\s+(\d+)", lines[15]).group(1))
            total = total_kb / 1024 / 1024  # GB
            free = free_kb / 1024 / 1024
            used = total - free
            mem_percent = (used / total * 100) if total > 0 else 0
            swap_total = swap_total_kb / 1024 / 1024
            swap_free = swap_free_kb / 1024 / 1024
            swap_used = swap_total - swap_free
            swap_percent = (swap_used / swap_total * 100) if swap_total > 0 else 0
            mem_color = get_color_by_percent(mem_percent)
            swap_color = get_color_by_percent(swap_percent)
            return {
                "total": round(total, 2),
                "used": round(used, 2),
                "percent": f"{mem_percent:.2f}%",
                "swap_total": round(swap_total, 2),
                "swap_used": round(swap_used, 2),
                "swap_percent": f"{swap_percent:.2f}%",
                "display": f'内存 {used:.2f}GB/{total:.2f}GB=<span style="color:{mem_color}">{mem_percent:.2f}%</span><br>Swap {swap_used:.2f}GB/{swap_total:.2f}GB=<span style="color:{swap_color}">{swap_percent:.2f}%</span>',
            }
        else:
            return {"display": "无法获取"}
    except Exception as e:
        print(f"获取内存信息失败: {e}")
        return {"display": "出错"}


# 获取硬盘信息（包含百分比）
def get_disk_info():
    try:
        stat = os.statvfs("/")
        total = (stat.f_blocks * stat.f_frsize) // (1024**3)  # GB
        free = (stat.f_bfree * stat.f_frsize) // (1024**3)
        used = total - free
        percent = (used / total * 100) if total > 0 else 0
        color = get_color_by_percent(percent)
        return {
            "total": total,
            "used": used,
            "percent": f"{percent:.2f}%",
            "display": f'硬盘 {used}GB/{total}GB=<span style="color:{color}">{percent:.2f}%</span>',
        }
    except Exception as e:
        print(f"获取硬盘信息失败: {e}")
        return {"display": "出错"}


# 获取 GPU 信息（需要 nvidia-smi 命令）
def get_gpu_info():
    def reformat_gpu_info(util, mem_used, mem_total, fan, power):
        import re

        digits = re.compile(r"[.0-9]+")

        def extract_first_match(text):
            match = digits.findall(text)
            return match[0] if match else "N/A"

        util_val = extract_first_match(util)
        mem_used_val = extract_first_match(mem_used)
        mem_total_val = extract_first_match(mem_total)
        fan_val = extract_first_match(fan)
        power_val = extract_first_match(power)
        return util_val, mem_used_val, mem_total_val, fan_val, power_val

    try:
        import subprocess

        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=utilization.gpu,memory.used,memory.total,fan.speed,power.draw", "--format=csv"],
            capture_output=True,
            text=True,
        )
        lines = result.stdout.splitlines()[1:]  # 跳过标题行
        gpu_detail = []
        display_list = []
        for i, line in enumerate(lines):
            util, mem_used, mem_total, fan, power = line.split(", ")
            util, mem_used, mem_total, fan, power = reformat_gpu_info(util, mem_used, mem_total, fan, power)
            try:
                mem_ratio = float(mem_used) / float(mem_total) * 100
            except:
                mem_ratio = 0
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


# 主函数
def main():
    args = parse_args()
    name = args.name
    master_host, master_port = args.master.split(":")
    master_port = int(master_port)

    # 创建 UDP 套接字
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    while True:
        # 收集系统信息
        info = {
            "name": {"display": name},
            "ip": {"display": get_ip_address()},
            "cpu": {"display": get_cpu_usage()},
            "memory": get_memory_info(),
            "disk": get_disk_info(),
            "gpu": get_gpu_info(),
            "timestamp": {"display": time.strftime("%Y-%m-%d %H:%M:%S")},
        }
        # 将信息编码为 JSON 并转换为 UTF-8 二进制
        try:
            message = json.dumps(info, ensure_ascii=False).encode("utf-8")
        except Exception as e:
            print(f"JSON 编码失败: {e}")
            continue

        # 发送到 master
        try:
            sock.sendto(message, (master_host, master_port))
            print(f"已发送数据到 {master_host}:{master_port}")
        except Exception as e:
            print(f"发送失败: {e}")

        # 每 120 秒发送一次
        time.sleep(120)


if __name__ == "__main__":
    main()
