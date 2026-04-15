#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
心率监测APP - Android端
接收ESP01通过WiFi发送的极简心率数据
协议格式: 心率,血氧,状态 (例: 78,95,0)
"""

import socket
import threading
import time
import json
from datetime import datetime
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.togglebutton import ToggleButton
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.graphics import Color, Line, Rectangle
from kivy.clock import Clock
from kivy.properties import NumericProperty, StringProperty, BooleanProperty, ListProperty
from kivy.core.audio import SoundLoader
from kivy.config import Config
from kivy.logger import Logger

# 配置
Config.set('graphics', 'width', '360')
Config.set('graphics', 'height', '640')
Config.set('graphics', 'resizable', False)

# ESP01配置
ESP01_IP = '192.168.4.1'  # ESP01 AP模式默认IP
ESP01_PORT = 8080
WIFI_SSID = 'HeartRateMonitor'  # ESP01创建的WiFi名称
WIFI_PASSWORD = '12345678'  # WiFi密码

class DataCache:
    """数据缓存管理"""
    def __init__(self, max_size=1000):
        self.max_size = max_size
        self.heart_rates = []
        self.spo2_values = []
        self.statuses = []
        self.timestamps = []
        self.cache_file = 'heart_rate_cache.json'
        self.load_cache()
    
    def add_data(self, heart_rate, spo2, status):
        """添加数据"""
        self.heart_rates.append(heart_rate)
        self.spo2_values.append(spo2)
        self.statuses.append(status)
        self.timestamps.append(datetime.now().isoformat())
        
        # 限制缓存大小
        if len(self.heart_rates) > self.max_size:
            self.heart_rates.pop(0)
            self.spo2_values.pop(0)
            self.statuses.pop(0)
            self.timestamps.pop(0)
        
        self.save_cache()
    
    def save_cache(self):
        """保存到文件"""
        try:
            data = {
                'heart_rates': self.heart_rates[-100:],  # 只保存最近100条
                'spo2_values': self.spo2_values[-100:],
                'statuses': self.statuses[-100:],
                'timestamps': self.timestamps[-100:]
            }
            with open(self.cache_file, 'w') as f:
                json.dump(data, f)
        except Exception as e:
            Logger.error(f'Cache save error: {e}')
    
    def load_cache(self):
        """从文件加载"""
        try:
            with open(self.cache_file, 'r') as f:
                data = json.load(f)
                self.heart_rates = data.get('heart_rates', [])
                self.spo2_values = data.get('spo2_values', [])
                self.statuses = data.get('statuses', [])
                self.timestamps = data.get('timestamps', [])
        except:
            pass
    
    def clear(self):
        """清空缓存"""
        self.heart_rates.clear()
        self.spo2_values.clear()
        self.statuses.clear()
        self.timestamps.clear()
        self.save_cache()

class WaveformWidget(BoxLayout):
    """波形图绘制组件"""
    heart_rates = ListProperty([0] * 100)
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.size_hint_y = 0.3
        self.bind(heart_rates=self.update_graph)
        self.bind(size=self.update_graph, pos=self.update_graph)
    
    def update_graph(self, *args):
        """更新波形图"""
        self.canvas.clear()
        with self.canvas:
            # 背景
            Color(0.1, 0.1, 0.15, 1)
            Rectangle(pos=self.pos, size=self.size)
            
            # 网格线
            Color(0.2, 0.2, 0.25, 1)
            for i in range(0, int(self.width), 30):
                Line(points=[self.pos[0] + i, self.pos[1], 
                            self.pos[0] + i, self.pos[1] + self.height], width=1)
            for i in range(0, int(self.height), 20):
                Line(points=[self.pos[0], self.pos[1] + i,
                            self.pos[0] + self.width, self.pos[1] + i], width=1)
            
            # 心率曲线
            if len(self.heart_rates) > 1:
                Color(0.9, 0.2, 0.4, 1)  # 红色
                points = []
                for i, hr in enumerate(self.heart_rates):
                    x = self.pos[0] + (i / len(self.heart_rates)) * self.width
                    # 归一化到0-200范围
                    y = self.pos[1] + (hr / 200.0) * self.height
                    points.extend([x, y])
                if len(points) >= 4:
                    Line(points=points, width=2)

class HeartRateApp(App):
    """主应用"""
    # 状态属性
    heart_rate = NumericProperty(0)
    spo2 = NumericProperty(0)
    status = NumericProperty(0)
    status_text = StringProperty('未连接')
    connection_status = StringProperty('未连接')
    is_connected = BooleanProperty(False)
    is_monitoring = BooleanProperty(False)
    alarm_active = BooleanProperty(False)
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.data_cache = DataCache()
        self.socket = None
        self.receive_thread = None
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 10
        self.last_data_time = 0
        self.timeout_seconds = 5
    
    def build(self):
        """构建UI"""
        layout = BoxLayout(orientation='vertical', padding=10, spacing=10)
        
        # 标题
        title = Label(
            text='[b]心率监测系统[/b]',
            markup=True,
            font_size='24sp',
            size_hint_y=0.08,
            color=(0.9, 0.9, 0.9, 1)
        )
        layout.add_widget(title)
        
        # 连接状态
        self.status_label = Label(
            text='状态: 未连接',
            font_size='14sp',
            size_hint_y=0.05,
            color=(0.7, 0.7, 0.7, 1)
        )
        layout.add_widget(self.status_label)
        
        # 心率显示
        hr_box = BoxLayout(orientation='vertical', size_hint_y=0.25, spacing=5)
        hr_box.canvas.before = []
        with hr_box.canvas.before:
            Color(0.15, 0.15, 0.2, 1)
            self.hr_rect = Rectangle(pos=hr_box.pos, size=hr_box.size)
        hr_box.bind(pos=self.update_hr_rect, size=self.update_hr_rect)
        
        self.hr_label = Label(
            text='--',
            font_size='72sp',
            bold=True,
            color=(0.9, 0.2, 0.4, 1)
        )
        hr_box.add_widget(self.hr_label)
        
        hr_unit = Label(
            text='BPM',
            font_size='16sp',
            color=(0.7, 0.7, 0.7, 1)
        )
        hr_box.add_widget(hr_unit)
        layout.add_widget(hr_box)
        
        # 血氧显示
        spo2_box = BoxLayout(orientation='horizontal', size_hint_y=0.12, spacing=10)
        spo2_label = Label(
            text='血氧饱和度:',
            font_size='16sp',
            color=(0.7, 0.7, 0.7, 1)
        )
        self.spo2_value = Label(
            text='-- %',
            font_size='24sp',
            bold=True,
            color=(0.3, 0.8, 0.9, 1)
        )
        spo2_box.add_widget(spo2_label)
        spo2_box.add_widget(self.spo2_value)
        layout.add_widget(spo2_box)
        
        # 波形图
        self.waveform = WaveformWidget()
        layout.add_widget(self.waveform)
        
        # 报警状态
        self.alarm_label = Label(
            text='[size=18]状态正常[/size]',
            markup=True,
            font_size='16sp',
            size_hint_y=0.08,
            color=(0.3, 0.9, 0.5, 1)
        )
        layout.add_widget(self.alarm_label)
        
        # 控制按钮
        btn_box = BoxLayout(orientation='horizontal', size_hint_y=0.1, spacing=10)
        
        self.connect_btn = Button(
            text='连接设备',
            font_size='16sp',
            background_color=(0.2, 0.6, 0.9, 1)
        )
        self.connect_btn.bind(on_press=self.toggle_connection)
        btn_box.add_widget(self.connect_btn)
        
        self.monitor_btn = ToggleButton(
            text='开始监测',
            font_size='16sp',
            background_color=(0.3, 0.8, 0.4, 1),
            state='normal'
        )
        self.monitor_btn.bind(on_press=self.toggle_monitoring)
        btn_box.add_widget(self.monitor_btn)
        
        layout.add_widget(btn_box)
        
        # 清除缓存按钮
        clear_btn = Button(
            text='清除历史数据',
            font_size='14sp',
            size_hint_y=0.07,
            background_color=(0.8, 0.3, 0.3, 1)
        )
        clear_btn.bind(on_press=self.clear_cache)
        layout.add_widget(clear_btn)
        
        # 定时检查连接
        Clock.schedule_interval(self.check_connection, 1.0)
        
        return layout
    
    def update_hr_rect(self, instance, value):
        """更新心率背景"""
        self.hr_rect.pos = instance.pos
        self.hr_rect.size = instance.size
    
    def toggle_connection(self, instance):
        """切换连接状态"""
        if self.is_connected:
            self.disconnect()
        else:
            self.connect()
    
    def connect(self):
        """连接到ESP01"""
        self.connection_status = '正在连接...'
        self.status_label.text = f'状态: 正在连接 {ESP01_IP}:{ESP01_PORT}'
        
        try:
            # 创建socket连接
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(5)
            self.socket.connect((ESP01_IP, ESP01_PORT))
            
            self.is_connected = True
            self.connection_status = '已连接'
            self.status_label.text = f'状态: 已连接到 {ESP01_IP}'
            self.connect_btn.text = '断开连接'
            self.connect_btn.background_color = (0.8, 0.3, 0.3, 1)
            
            # 启动接收线程
            self.receive_thread = threading.Thread(target=self.receive_data, daemon=True)
            self.receive_thread.start()
            
            self.reconnect_attempts = 0
            self.last_data_time = time.time()
            
        except Exception as e:
            Logger.error(f'Connection error: {e}')
            self.show_popup('连接失败', f'无法连接到设备\n{str(e)}')
            self.connection_status = '连接失败'
            self.status_label.text = '状态: 连接失败'
    
    def disconnect(self):
        """断开连接"""
        self.is_connected = False
        self.is_monitoring = False
        
        if self.socket:
            try:
                self.socket.close()
            except:
                pass
            self.socket = None
        
        self.connection_status = '未连接'
        self.status_label.text = '状态: 未连接'
        self.connect_btn.text = '连接设备'
        self.connect_btn.background_color = (0.2, 0.6, 0.9, 1)
        self.monitor_btn.state = 'normal'
        self.monitor_btn.text = '开始监测'
    
    def receive_data(self):
        """接收数据线程"""
        buffer = ''
        while self.is_connected and self.socket:
            try:
                data = self.socket.recv(1024)
                if not data:
                    # 连接断开
                    Clock.schedule_once(lambda dt: self.handle_disconnect(), 0)
                    break
                
                buffer += data.decode('utf-8', errors='ignore')
                
                # 解析数据（格式: 心率,血氧,状态\n）
                while '\n' in buffer:
                    line, buffer = buffer.split('\n', 1)
                    line = line.strip()
                    
                    if line and self.is_monitoring:
                        self.parse_data(line)
                
            except socket.timeout:
                continue
            except Exception as e:
                Logger.error(f'Receive error: {e}')
                Clock.schedule_once(lambda dt: self.handle_disconnect(), 0)
                break
    
    def parse_data(self, data_str):
        """解析数据"""
        try:
            # 格式: 心率,血氧,状态
            parts = data_str.split(',')
            if len(parts) >= 3:
                heart_rate = int(parts[0])
                spo2 = int(parts[1])
                status = int(parts[2])
                
                # 更新UI（在主线程）
                Clock.schedule_once(
                    lambda dt, hr=heart_rate, sp=spo2, st=status: 
                    self.update_display(hr, sp, st), 0
                )
                
                # 缓存数据
                self.data_cache.add_data(heart_rate, spo2, status)
                self.last_data_time = time.time()
                
        except Exception as e:
            Logger.error(f'Parse error: {e}, data: {data_str}')
    
    def update_display(self, heart_rate, spo2, status):
        """更新显示"""
        self.heart_rate = heart_rate
        self.spo2 = spo2
        self.status = status
        
        # 更新心率
        self.hr_label.text = str(heart_rate)
        
        # 更新血氧
        self.spo2_value.text = f'{spo2} %'
        
        # 更新波形图
        hr_list = list(self.waveform.heart_rates)
        hr_list.append(heart_rate)
        if len(hr_list) > 100:
            hr_list.pop(0)
        self.waveform.heart_rates = hr_list
        
        # 更新状态
        if status == 0:
            self.alarm_label.text = '[size=18]状态正常[/size]'
            self.alarm_label.color = (0.3, 0.9, 0.5, 1)
            self.alarm_active = False
        elif status == 1:
            self.alarm_label.text = '[size=18][b]注意：心率异常[/b][/size]'
            self.alarm_label.color = (0.9, 0.7, 0.2, 1)
            self.alarm_active = True
        else:
            self.alarm_label.text = '[size=18][b]警告：严重异常！[/b][/size]'
            self.alarm_label.color = (1, 0.2, 0.2, 1)
            self.alarm_active = True
    
    def toggle_monitoring(self, instance):
        """切换监测状态"""
        if not self.is_connected:
            self.show_popup('提示', '请先连接设备')
            instance.state = 'normal'
            return
        
        self.is_monitoring = instance.state == 'down'
        if self.is_monitoring:
            instance.text = '停止监测'
            self.status_label.text = '状态: 监测中...'
        else:
            instance.text = '开始监测'
            self.status_label.text = '状态: 已连接（未监测）'
    
    def check_connection(self, dt):
        """检查连接状态"""
        if self.is_connected and self.is_monitoring:
            # 检查超时
            if time.time() - self.last_data_time > self.timeout_seconds:
                self.handle_disconnect()
    
    def handle_disconnect(self):
        """处理断连"""
        if self.is_connected:
            self.disconnect()
            self.show_popup('连接断开', '与设备的连接已断开\n正在尝试重连...')
            
            # 自动重连
            if self.reconnect_attempts < self.max_reconnect_attempts:
                self.reconnect_attempts += 1
                Clock.schedule_once(lambda dt: self.connect(), 2)
    
    def clear_cache(self, instance):
        """清除缓存"""
        self.data_cache.clear()
        self.waveform.heart_rates = [0] * 100
        self.show_popup('提示', '历史数据已清除')
    
    def show_popup(self, title, message):
        """显示弹窗"""
        popup = Popup(
            title=title,
            content=Label(text=message, font_size='16sp'),
            size_hint=(0.8, 0.4)
        )
        popup.open()
    
    def on_stop(self):
        """应用退出"""
        self.disconnect()
        self.data_cache.save_cache()

if __name__ == '__main__':
    HeartRateApp().run()