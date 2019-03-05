# -*- coding: UTF-8 -*-
from BaseHTTPServer import HTTPServer, BaseHTTPRequestHandler
from io import StringIO
# urlparse v-2.7 urllib.parse v-3.0
import json, urlparse, os
import subprocess, re
import pycurl, sys, os, time
import geoip2.database
import socket
import Queue, threading


class RequestHandler(BaseHTTPRequestHandler):
    def _set_headers(self):
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()

    def do_POST(self):
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)
        post_data = urlparse.parse_qs(post_data)
        test_url = post_data['url'][0]
        action = post_data['action'][0]
        response = {
            'status': 'SUCCESS',
        }
        if action == 'speed_test':
            parse_ip_data = parse_ip(test_url)
            speed_data = speed(test_url)
            response.update(parse_ip_data)
            response.update(speed_data)
        elif action == 'speed_monitor':
            response_list = []
            test_url_list = test_url.split(',')
            # 线程队列
            work_queue = Queue.Queue(20)
            work_threads = []

            # 定义线程
            class MyThread(threading.Thread):
                def __init__(self, thread_id, name, queue):
                    threading.Thread.__init__(self)
                    self.threadID = thread_id
                    self.name = name
                    self.queue = queue

                def run(self):
                    url = self.queue.get()
                    temp = {
                        'url': url
                    }
                    # temp.update(parse_ip(url))
                    temp.update(speed(url))
                    response_list.append(temp)

            # 创建新线程 & 填充队列
            for i in test_url_list:
                index = test_url_list.index(i) + 1
                thread = MyThread(index, 'Thread-' + str(index), work_queue)
                thread.start()
                work_threads.append(thread)
                # 填充队列
                work_queue.put(i)
            # 等待队列清空
            while not work_queue.empty():
                pass
            # 等待所有线程完成
            for t in work_threads:
                t.join()
            # print "Exiting Main Thread"
            response.update({
                'list': response_list
            })

        self._set_headers()
        self.wfile.write(json.dumps(response))


def ping(url):
    p = subprocess.Popen(['ping', '-c', '4', "-w", "10", url],
                         stdout=subprocess.PIPE)
    stdout, stderr = p.communicate()
    if p.returncode == 0:
        out = stdout.decode('ASCII')
        reg_ip = r'\(\d+\.\d+\.\d+\.\d+\)'  ## PING www.wshifen.com (103.235.46.39) 56(84) bytes of data.
        reg_lost = r'\ \d+%'  ## 4 packets transmitted, 4 received, 0% packet loss, time 3004ms
        reg_time = u'\ \d+\.\d+\/\d+\.\d+\/\d+\.\d+\/\d+\.\d+'  ## rtt min/avg/max/mdev = 1.030/1.171/1.536/0.212 ms
        ip = re.search(reg_ip, out)
        lost = re.search(reg_lost, out)
        time = re.search(reg_time, out).group()[1:].split('/')
        return {
            'ip': ip.group()[1:-1],
            'ip_location': get_ip_location(ip.group()[1:-1]),
            'lost_percent': lost.group()[1:],
            'ping_min_time': time[0],
            'ping_ave_time': time[1],
            'ping_max_time': time[2],
        }
    else:
        return {}


def parse_ip(url):
    try:
        ip = socket.gethostbyname(url)
    except  Exception as e:
        print "parse_ip error:" + str(e)
        return {'parse_msg': 'error', 'ip': 'Can\'t Resolve'}
    return {
        'parse_msg': 'success',
        'ip': ip,
        'ip_location': get_ip_location(ip),
    }


def speed(url):
    idc = Idc()
    c = pycurl.Curl()
    c.setopt(pycurl.WRITEFUNCTION, idc.body_callback)
    c.setopt(pycurl.URL, url)
    c.setopt(pycurl.FRESH_CONNECT, 1)  # 防止缓存
    c.setopt(pycurl.MAXREDIRS, 5)  # 重定向次数
    c.setopt(pycurl.CONNECTTIMEOUT, 5)  # 链接超时
    c.setopt(pycurl.TIMEOUT, 5)  # 下载超时
    c.setopt(pycurl.USERAGENT,
             "Mozilla/5.2 (compatible; MSIE 6.0; Windows NT 5.1; SV1; .NET CLR 1.1.4322; .NET CLR 2.0.50324)")  # 模拟浏览器
    try:
        c.perform()
    except pycurl.error as e:
        print "connecion error:" + str(e)
        c.close()
        return {'speed_msg': 'error', 'http_code': e[1]}

    http_code = c.getinfo(pycurl.HTTP_CODE)
    dns_resolve_time = c.getinfo(pycurl.NAMELOOKUP_TIME)
    http_conn_time = c.getinfo(pycurl.CONNECT_TIME)
    http_pre_trans = c.getinfo(pycurl.PRETRANSFER_TIME)
    http_start_trans = c.getinfo(pycurl.STARTTRANSFER_TIME)
    http_total_time = c.getinfo(pycurl.TOTAL_TIME)
    http_size_download = c.getinfo(pycurl.SIZE_DOWNLOAD)
    http_speed_download = c.getinfo(pycurl.SPEED_DOWNLOAD)

    # print ('HTTP响应状态： %d' % http_code)
    # print ('DNS解析时间：%.2f ms' % (dns_resolve_time * 1000))
    # print ('建立连接时间： %.2f ms' % (http_conn_time * 1000))
    # print ('准备传输时间： %.2f ms' % (http_pre_trans * 1000))
    # print ("传输开始时间： %.2f ms" % (http_start_trans * 1000))
    # print ("传输结束时间： %.2f ms" % (http_total_time * 1000))
    # print ("下载数据包大小： %d bytes/s" % http_size_download)
    # print ("平均下载速度： %d k/s" % (http_speed_download / 1024))

    print {
        'speed_msg': 'success',
        'http_code': http_code,
        'dns_resolve_time': '%.2f ms' % (dns_resolve_time * 1000),
        'http_total_time': '%.2f ms' % (http_total_time * 1000),
        'http_conn_time': '%.2f ms' % (http_conn_time * 1000),
        'http_pre_trans': '%.2f ms' % (http_pre_trans * 1000),
        'http_start_trans': '%.2f ms' % (http_start_trans * 1000),
        'http_size_download': '%.2f kb' % (http_size_download / 1024),
        'http_speed_download': '%.2f mb/s' % (http_speed_download / 1024 / 1024)
    }
    return {
        'speed_msg': 'success',
        'http_code': http_code,
        'dns_resolve_time': '%.2f ms' % (dns_resolve_time * 1000),
        'http_total_time': '%.2f ms' % (http_total_time * 1000),
        'http_conn_time': '%.2f ms' % (http_conn_time * 1000),
        'http_pre_trans': '%.2f ms' % (http_pre_trans * 1000),
        'http_start_trans': '%.2f ms' % (http_start_trans * 1000),
        'http_size_download': '%.2f kb' % (http_size_download / 1024),
        'http_speed_download': '%.2f mb/s' % (http_speed_download / 1024 / 1024)
    }


def get_ip_location(ip):
    reader = geoip2.database.Reader('./lib/GeoLite2-City.mmdb')
    response = reader.city(ip)
    continent = response.continent.names["zh-CN"] if response.continent.names.has_key("zh-CN") else ''
    country = response.country.names["zh-CN"] if response.country.names.has_key("zh-CN") else ''
    subdivisions = response.subdivisions.most_specific.names["zh-CN"] if \
        response.subdivisions.most_specific.names.has_key("zh-CN") else ''
    city = response.city.names["zh-CN"] if response.city.names.has_key("zh-CN") else ''
    return (continent + country + subdivisions + city).encode('utf-8')


# 定义IDC存放curl返回值
class Idc:
    def __init__(self):
        self.contents = ''

    def body_callback(self, buf):
        self.contents = self.contents + buf


def run():
    port = 2019
    print('Listening on localhost:%s' % port)
    server = HTTPServer(('0.0.0.0', port), RequestHandler)
    server.serve_forever()


if __name__ == '__main__':
    run()
