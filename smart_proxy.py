import socket
import threading
import json
import os
import time
from datetime import datetime

class SmartStratumProxy:
    def __init__(self, local_port):
        self.local_port = local_port
        self.remote_host = "ltc.viabtc.io"
        self.remote_ports = [25, 443, 3333]  # پورت‌های شما
        self.working_port = None
        self.server_socket = None
        self.last_check = 0
        
    def log(self, message):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] {message}")
        
    def test_connection(self, port):
        """تست اتصال به پورت مشخص"""
        try:
            test_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            test_socket.settimeout(5)
            result = test_socket.connect_ex((self.remote_host, port))
            test_socket.close()
            return result == 0
        except:
            return False
    
    def find_working_port(self):
        """پیدا کردن پورت کارآمد"""
        self.log("Testing connection to all ports...")
        
        for port in self.remote_ports:
            self.log(f"Testing port {port}...")
            if self.test_connection(port):
                self.log(f"✓ Port {port} is working!")
                return port
            else:
                self.log(f"✗ Port {port} failed")
        
        self.log("⚠️  No working port found!")
        return None
    
    def get_working_port(self):
        """دریافت پورت کارآمد با cache"""
        current_time = time.time()
        
        # اگر 5 دقیقه از آخرین چک گذشته، دوباره تست کن
        if current_time - self.last_check > 300:  # 5 minutes
            self.working_port = self.find_working_port()
            self.last_check = current_time
        
        return self.working_port
    
    def handle_client(self, client_socket):
        client_addr = client_socket.getpeername()
        self.log(f"Client connected from {client_addr}")
        
        try:
            # پیدا کردن پورت کارآمد
            working_port = self.get_working_port()
            if not working_port:
                self.log("No working port available, retrying...")
                working_port = self.find_working_port()
                
            if not working_port:
                self.log("All ports failed, closing client connection")
                client_socket.close()
                return
            
            # اتصال به سرور اصلی
            remote_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            remote_socket.settimeout(10)
            remote_socket.connect((self.remote_host, working_port))
            
            self.log(f"Connected to {self.remote_host}:{working_port}")
            
            # تعریف thread برای forward کردن داده‌ها
            def forward_data(source, destination, direction):
                try:
                    while True:
                        data = source.recv(4096)
                        if not data:
                            break
                        destination.send(data)
                        
                        # log کردن برای debugging (فقط خط اول)
                        if direction == "client->server":
                            try:
                                decoded = data.decode('utf-8').strip().split('\n')[0]
                                if len(decoded) > 100:
                                    decoded = decoded[:100] + "..."
                                self.log(f"C->S: {decoded}")
                            except:
                                pass
                        else:
                            try:
                                decoded = data.decode('utf-8').strip().split('\n')[0]
                                if len(decoded) > 100:
                                    decoded = decoded[:100] + "..."
                                self.log(f"S->C: {decoded}")
                            except:
                                pass
                                
                except Exception as e:
                    if "Connection reset" not in str(e):
                        self.log(f"Forward error ({direction}): {e}")
                finally:
                    try:
                        source.close()
                        destination.close()
                    except:
                        pass
            
            # شروع thread ها
            client_to_server = threading.Thread(
                target=forward_data, 
                args=(client_socket, remote_socket, "client->server")
            )
            server_to_client = threading.Thread(
                target=forward_data, 
                args=(remote_socket, client_socket, "server->client")
            )
            
            client_to_server.daemon = True
            server_to_client.daemon = True
            
            client_to_server.start()
            server_to_client.start()
            
            # منتظر ماندن تا یکی از thread ها تمام شود
            while client_to_server.is_alive() and server_to_client.is_alive():
                time.sleep(0.1)
            
        except Exception as e:
            self.log(f"Client handler error: {e}")
        finally:
            try:
                client_socket.close()
            except:
                pass
            self.log(f"Client {client_addr} disconnected")
    
    def start(self):
        try:
            # ابتدا پورت کارآمد رو پیدا کن
            self.working_port = self.find_working_port()
            if not self.working_port:
                self.log("❌ Cannot start proxy - no working remote port found!")
                return
            
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind(('0.0.0.0', self.local_port))
            self.server_socket.listen(5)
            
            self.log(f"🚀 Smart Stratum Proxy started on port {self.local_port}")
            self.log(f"📡 Currently using {self.remote_host}:{self.working_port}")
            self.log(f"🔄 Available ports: {', '.join(map(str, self.remote_ports))}")
            
            while True:
                try:
                    client_socket, addr = self.server_socket.accept()
                    client_thread = threading.Thread(
                        target=self.handle_client, 
                        args=(client_socket,)
                    )
                    client_thread.daemon = True
                    client_thread.start()
                except Exception as e:
                    self.log(f"Accept error: {e}")
                    time.sleep(1)
                
        except Exception as e:
            self.log(f"Server error: {e}")
        finally:
            if self.server_socket:
                self.server_socket.close()

if __name__ == "__main__":
    # تنظیمات
    LOCAL_PORT = int(os.environ.get('PORT', 8080))
    
    # شروع smart proxy
    proxy = SmartStratumProxy(LOCAL_PORT)
    proxy.start()
