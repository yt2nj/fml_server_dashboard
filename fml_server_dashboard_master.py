# python fml_server_dashboard_master.py --data_port 9901 --web_port 9900
# 功能：接收 slave 发送的 JSON 格式系统信息并通过简单的 HTTP 服务展示

import socket
import argparse
import threading
import time
import http.server
import socketserver
import json


# 解析命令行参数
def parse_args():
    parser = argparse.ArgumentParser(description="服务器监控主节点")
    parser.add_argument("--data_port", type=int, required=True, help="接收数据的 UDP 端口")
    parser.add_argument("--web_port", type=int, required=True, help="网页服务的 HTTP 端口")
    return parser.parse_args()


# 存储节点信息的全局字典
nodes = {}
nodes_lock = threading.Lock()


# UDP 服务线程，接收 slave 数据
def udp_server(port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("", port))
    print(f"UDP 服务启动在端口 {port}")

    while True:
        data, addr = sock.recvfrom(1024 * 16)
        try:
            # 解码 UTF-8 二进制数据并解析 JSON
            message = data.decode("utf-8")
            node_info = json.loads(message)
            with nodes_lock:
                nodes[node_info["name"]["display"]] = node_info
        except Exception as e:
            print(f"处理数据失败: {e}")


# HTTP 服务处理类
class DashboardHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.end_headers()

        # 生成简单的 HTML 页面
        html = """<html><head><title>FML服务器仪表盘</title>
        <meta charset="utf-8">
        <meta http-equiv="refresh" content="30">
        <style>
            body { font-family: Consolas, Monaco, monospace; background: #f7f7f7; }
            h1 { text-align: center; }
            table { border-collapse: collapse; width: 98%; margin: 0 auto; background: #fff; box-shadow: 0 2px 8px #ccc; }
            th, td { border: 1px solid #bbb; padding: 10px 8px; text-align: center; }
            th { background: #e3e3e3; }
            tr:nth-child(even) { background: #f2f2f2; }
        </style>
        </head><body><h1>FML服务器仪表盘</h1><table>
        <tr><th>节点名称</th><th>CPU/内存/硬盘</th><th>GPU</th></tr>"""

        with nodes_lock:
            for name, info in nodes.items():
                html += f"<tr>"
                html += f'<td>{info.get("name").get("display")}<br>[{info.get("ip").get("display")}]<br>({info.get("timestamp").get("display")})</td>'
                html += f'<td>{info.get("cpu").get("display")}<br>{info.get("memory").get("display")}<br>{info.get("disk").get("display")}</td>'
                html += f'<td>{info.get("gpu").get("display")}</td>'
                html += f"</tr>"

        html += "</table>"
        html += '<p><a href="https://github.com/yt2nj/fml_server_dashboard">详情请见GitHub.</a></p>'
        html += "</body></html>"
        self.wfile.write(html.encode("utf-8"))


# 主函数
def main():
    args = parse_args()
    data_port = args.data_port
    web_port = args.web_port

    # 启动 UDP 服务线程
    udp_thread = threading.Thread(target=udp_server, args=(data_port,), daemon=True)
    udp_thread.start()

    # 启动 HTTP 服务
    with socketserver.TCPServer(("", web_port), DashboardHandler) as httpd:
        print(f"HTTP 服务启动在端口 {web_port}")
        try:
            httpd.serve_forever()
        except:
            print("服务停止")
            httpd.server_close()


if __name__ == "__main__":
    main()
