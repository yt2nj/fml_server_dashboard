# python fml_server_dashboard_master.py --data_port 9901 --web_port 9900
# 功能：接收 slave 发送的 JSON 格式系统信息并通过简单的 HTTP 服务展示

import socket
import argparse
import threading
import time
import http.server
import socketserver
import json

from datetime import datetime, timedelta


# ---------- 解析命令行 ----------
def parse_args():
    parser = argparse.ArgumentParser(description="服务器监控主节点")
    parser.add_argument("--data_port", type=int, required=True, help="接收数据的 UDP 端口")
    parser.add_argument("--web_port", type=int, required=True, help="网页服务的 HTTP 端口")
    parser.add_argument("--white_list", type=str, default="", help="白名单，格式: name1,ip1;name2,ip2 允许为空")
    return parser.parse_args()


# ---------- 全局变量 ----------
nodes = {}
nodes_lock = threading.Lock()
white_set = set()


# ---------- 把白名单字符串解析成 set ----------
def build_white_set(white_str: str):
    """
    输入: 'GPU-X,1.2.3.4;GPU-Y,5.6.7.8'
    输出: {('GPU-X', '1.2.3.4'), ('GPU-Y', '5.6.7.8')}
    """
    white_set = set()
    if not white_str.strip().strip(";"):
        return white_set
    for seg in white_str.strip().split(";"):
        seg = seg.strip()
        if len(seg) <= 8 or not "," in seg:
            continue
        name, ip = seg.split(",")
        white_set.add((name.strip(), ip.strip()))
    return white_set


# ---------- 后台清理线程 ----------
def cleanup_dead():

    # time_str 格式：2025-09-19 17:42:00
    def _older_than_2h(time_str, now):
        if not time_str:
            return True
        try:
            node_time = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
            return node_time < now - timedelta(hours=2)
        except Exception:
            return True

    while True:
        now = datetime.now()
        with nodes_lock:
            to_delete = [name for name, info in nodes.items() if _older_than_2h(info.get("timestamp", {}).get("display"), now)]
            for name in to_delete:
                del nodes[name]
            if to_delete:
                print(f"删除 {len(to_delete)} 个过期节点: {to_delete}")
        time.sleep(120)


# ---------- UDP 服务线程 ----------
def udp_server(port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("", port))
    print(f"UDP 服务启动在端口 {port}")

    while True:
        data, addr = sock.recvfrom(1024 * 16)
        try:
            message = data.decode("utf-8")
            node_info = json.loads(message)

            node_name = node_info["name"]["display"]
            node_ip = node_info["ip"]["display"]

            # 白名单过滤
            if white_set and (node_name, node_ip) not in white_set:
                continue

            # 解析本次上报的 timestamp
            new_ts_str = node_info["timestamp"]["display"]
            new_dt = datetime.strptime(new_ts_str, "%Y-%m-%d %H:%M:%S")

            with nodes_lock:
                # 取出内存里上一次的 timestamp
                old_ts_str = nodes.get(node_name, {}).get("timestamp", {}).get("display", "")
                # 100 秒内重复，直接丢弃
                if old_ts_str:
                    old_dt = datetime.strptime(old_ts_str, "%Y-%m-%d %H:%M:%S")
                    if (new_dt - old_dt).total_seconds() <= 100:
                        continue

                # 真正更新
                nodes[node_name] = node_info

        except Exception as e:
            print(f"处理数据失败: {e}")


# ---------- HTTP 服务 ----------
class DashboardHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.end_headers()

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

        with nodes_lock:
            for name, info in nodes.items():
                html += f"<tr>"
                html += f'<td>{info.get("name").get("display")}<br>[{info.get("ip").get("display")}]<br>({info.get("timestamp").get("display")})</td>'
                html += f'<td>{info.get("cpu").get("display")}<br>{info.get("memory").get("display")}<br>{info.get("disk").get("display")}</td>'
                html += f'<td>{info.get("gpu").get("display")}</td>'
                html += f"</tr>\n"

        html += "</table>\n"
        html += '<p><a href="https://github.com/yt2nj/fml_server_dashboard">详情请见GitHub.</a></p>\n'
        html += "</body>\n</html>"
        self.wfile.write(html.encode("utf-8"))


# ---------- 主函数 ----------
def main():
    args = parse_args()
    data_port = args.data_port
    web_port = args.web_port

    global white_set
    white_set = build_white_set(args.white_list)
    if white_set:
        print("白名单已启用:", white_set)
    else:
        print("白名单未启用（允许所有节点）")

    threading.Thread(target=cleanup_dead, daemon=True).start()
    threading.Thread(target=udp_server, args=(data_port,), daemon=True).start()

    with socketserver.TCPServer(("", web_port), DashboardHandler) as httpd:
        print(f"HTTP 服务启动在端口 {web_port}")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("服务停止")
            httpd.server_close()


if __name__ == "__main__":
    main()
