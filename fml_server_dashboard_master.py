# 启动命令示例：python fml_server_dashboard_master.py --data_port 9901 --web_port 9900
# 功能：接收slave节点发送的JSON格式系统信息，并通过HTTP服务提供Web仪表盘展示

# ---------- 导入必要的网络、线程、时间等系统库 ----------
import socket
import argparse
import threading
import time
import http.server
import socketserver
import json

from datetime import datetime, timedelta


# ---------- 解析命令行参数 ----------
def parse_args():
    parser = argparse.ArgumentParser(description="服务器监控主节点")
    parser.add_argument("--data_port", type=int, required=True, help="接收数据的 UDP 端口")
    parser.add_argument("--web_port", type=int, required=True, help="网页服务的 HTTP 端口")
    parser.add_argument("--white_list", type=str, default="", help="白名单，格式: name1,ip1;name2,ip2 允许为空")
    return parser.parse_args()


# ---------- 全局变量：存储节点信息和白名单 ----------
nodes = {}
nodes_lock = threading.Lock()
white_set = set()


# ---------- 解析白名单字符串，构建白名单集合 ----------
def build_white_set(white_str: str):
    """
    将白名单字符串解析为集合格式
    输入示例: 'GPU-X,1.2.3.4;GPU-Y,5.6.7.8'
    输出示例: {('GPU-X', '1.2.3.4'), ('GPU-Y', '5.6.7.8')}
    """
    white_set = set()
    # 检查输入是否为空或只包含分号
    if not white_str.strip().strip(";"):
        return white_set
    # 按分号分割并解析每个条目
    for seg in white_str.strip().split(";"):
        seg = seg.strip()
        if len(seg) <= 8 or not "," in seg:
            continue
        name, ip = seg.split(",")
        white_set.add((name.strip(), ip.strip()))
    return white_set


# ---------- 后台清理线程：定期清理超时的节点信息 ----------
def cleanup_dead():

    # 辅助函数：检查时间戳是否超过2小时
    def _older_than_2h(time_str, now):
        if not time_str:
            return True
        try:
            node_time = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
            return node_time < now - timedelta(hours=2)
        except Exception:
            return True

    # 持续运行的清理循环
    while True:
        now = datetime.now()
        # 线程安全地访问nodes字典，找出过期节点
        with nodes_lock:
            to_delete = [name for name, info in nodes.items() if _older_than_2h(info.get("timestamp", {}).get("display"), now)]
            for name in to_delete:
                del nodes[name]
            if to_delete:
                print(f"删除 {len(to_delete)} 个过期节点: {to_delete}")
        # 每120秒检查一次
        time.sleep(120)


# ---------- UDP服务线程：接收并处理slave节点发送的数据 ----------
def udp_server(port):
    # 创建UDP socket并绑定到指定端口
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("", port))
    print(f"UDP 服务启动在端口 {port}")

    # 持续接收数据的主循环
    while True:
        # 接收UDP数据包，最大16KB
        data, addr = sock.recvfrom(1024 * 16)
        try:
            # 解码JSON数据并提取节点信息
            message = data.decode("utf-8")
            node_info = json.loads(message)

            node_name = node_info["name"]["display"]
            node_ip = node_info["ip"]["display"]

            # 如果设置了白名单则进行过滤检查
            if white_set and (node_name, node_ip) not in white_set:
                continue

            # 解析并验证时间戳，避免重复数据
            new_ts_str = node_info["timestamp"]["display"]
            new_dt = datetime.strptime(new_ts_str, "%Y-%m-%d %H:%M:%S")

            # 线程安全地更新节点信息
            with nodes_lock:
                # 获取上次记录的时间戳
                old_ts_str = nodes.get(node_name, {}).get("timestamp", {}).get("display", "")
                # 如果100秒内有重复数据则丢弃
                if old_ts_str:
                    old_dt = datetime.strptime(old_ts_str, "%Y-%m-%d %H:%M:%S")
                    if (new_dt - old_dt).total_seconds() <= 100:
                        continue

                # 更新节点信息到内存
                nodes[node_name] = node_info

        except Exception as e:
            print(f"处理数据失败: {e}")


# ---------- HTTP服务处理器：生成Web仪表盘页面 ----------
class DashboardHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        # 设置HTTP响应头
        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.end_headers()

        # 生成HTML页面的头部和样式
        html = """<html>
<head>
<title>FML服务器仪表盘</title>
<meta charset="utf-8">
<style>
    body{font-family:Consolas,Monaco,monospace;background:#f7f7f7;}
    h1{text-align:center;}
    table{border-collapse:collapse;border-radius:8px;overflow:hidden;width:max-content;max-width:98%;margin:0 auto;background:#fff;box-shadow:0 2px 8px #ccc;}
    th,td{border:1px solid #bbb;padding:10px 8px;text-align:center;}
    th{background:#e3e3e3;}
    tr:nth-child(even){background:#f2f2f2;}
</style>
</head>
<body>
<h1>FML服务器仪表盘</h1>
<table>
<tr><th>节点名称</th><th>CPU/内存/硬盘</th><th>GPU</th></tr>\n"""

        # 线程安全地读取节点数据并生成表格行
        with nodes_lock:
            for name, info in nodes.items():
                html += f"<tr>"
                html += f'<td>{info.get("name").get("display")}<br>[{info.get("ip").get("display")}]<br>({info.get("timestamp").get("display")})</td>'
                html += f'<td>{info.get("cpu").get("display")}<br>{info.get("memory").get("display")}<br>{info.get("disk").get("display")}</td>'
                html += f'<td>{info.get("gpu").get("display")}</td>'
                html += f"</tr>\n"

        # 生成页面尾部
        html += "</table>\n"
        html += '<p><a href="https://github.com/yt2nj/fml_server_dashboard">详情请见GitHub.</a></p>\n'
        html += "</body>\n</html>"
        # 发送HTML内容
        self.wfile.write(html.encode("utf-8"))


# ---------- 主程序入口：启动所有服务线程 ----------
def main():
    # 解析命令行参数
    args = parse_args()
    data_port = args.data_port
    web_port = args.web_port

    # 构建白名单集合并输出状态信息
    global white_set
    white_set = build_white_set(args.white_list)
    if white_set:
        print("白名单已启用:", white_set)
    else:
        print("白名单未启用（允许所有节点）")

    # 启动后台线程：清理过期节点和UDP数据接收
    threading.Thread(target=cleanup_dead, daemon=True).start()
    threading.Thread(target=udp_server, args=(data_port,), daemon=True).start()

    # 启动HTTP服务器提供Web仪表盘
    with socketserver.TCPServer(("", web_port), DashboardHandler) as httpd:
        print(f"HTTP 服务启动在端口 {web_port}")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("服务停止")
            httpd.server_close()


if __name__ == "__main__":
    main()
