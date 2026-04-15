#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
心率监测APP - Android端（STM32H7 + ESP01专用版）
功能：实时心率、实时时间、评分、波形图、检测总结
协议：心率,评分,状态,时间戳\n
"""

import socket
import threading
import time
from datetime import datetime
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.scrollview import ScrollView
from kivy.graphics import Color, Line, Rectangle
from kivy.clock import Clock
from kivy.properties import NumericProperty, StringProperty, BooleanProperty, ListProperty
from kivy.config import Config
from kivy.logger import Logger

Config.set('graphics', 'width', '360')
Config.set('graphics', 'height', '720')

# ESP01配置（AP模式）
ESP01_IP = '192.168.4.1'
ESP01_PORT = 8080

class WaveformWidget(BoxLayout):
    """心率波形图组件"""
    heart_rates = ListProperty([0] * 60)
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.size_hint_y = 0.25
        self.bind(heart_rates=self.update_graph)
        self.bind(size=self.update_graph, pos=self.update_graph)
    
    def update_graph(self, *args):
        """绘制波形图"""
        self.canvas.clear()
        with self.canvas:
            # 深色背景
            Color(0.08, 0.08, 0.12, 1)
            Rectangle(pos=self.pos, size=self.size)
            
            # 网格线
            Color(0.15, 0.15, 0.2, 1)
            for i in range(0, int(self.width), 20):
                Line(points=[self.pos[0] + i, self.pos[1], 
                            self.pos[0] + i, self.pos[1] + self.height], width=1)
            for i in range(0, int(self.height), 15):
                Line(points=[self.pos[0], self.pos[1] + i,
                            self.pos[0] + self.width, self.pos[1] + i], width=1)
            
            # 心率曲线（红色）
            if len(self.heart_rates) > 1:
                Color(0.95, 0.25, 0.35, 1)
                points = []
                for i, hr in enumerate(self.heart_rates):
                    x = self.pos[0] + (i / len(self.heart_rates)) * self.width
                    y = self.pos[1] + ((hr - 40) / 160.0) * self.height  # 40-200范围
                    y = max(self.pos[1], min(self.pos[1] + self.height, y))
                    points.extend([x, y])
                if len(points) >= 4:
                    Line(points=points, width=2.5)

class SummaryWidget(ScrollView):
    """检测总结组件"""
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.size_hint_y = 0.2
        self.summary_text = ""
        
        layout = BoxLayout(orientation='vertical', size_hint_y=None, padding=10, spacing=5)
        layout.bind(minimum_height=layout.setter('height'))
        
        self.summary_label = Label(
            text='等待数据...',
            markup=True,
            font_size='14sp',
            size_hint_y=None,
            height=150,
            color=(0.8, 0.8, 0.8, 1),
            halign='left',
            valign='top'
        )
        self.summary_label.bind(size=self.summary_label.setter('text_size'))
        layout.add_widget(self.summary_label)
        self.add_widget(layout)
    
    def update_summary(self, hr_avg, hr_min, hr_max, score_avg, abnormal_count, total_count, duration):
        """更新检测总结"""
        if total_count == 0:
            self.summary_label.text = '等待数据...'
            return
        
        # 计算健康评级
        health_level = "优秀" if score_avg >= 90 else "良好" if score_avg >= 80 else "正常" if score_avg >= 70 else "注意" if score_avg >= 60 else "需关注"
        
        # 异常比例
        abnormal_ratio = (abnormal_count / total_count) * 100
        
        # 生成总结文本
        summary = f"""[b][color=#4ecca3]📊 检测总结[/color][/b]

[color=#e94560]❤ 平均心率：[/color]{hr_avg:.1f} BPM
[color=#e94560]📉 心率范围：[/color]{hr_min}-{hr_max} BPM
[color=#3a86ff]⭐ 平均评分：[/color]{score_avg:.1f} 分
[color=#ffbe0b]🏆 健康评级：[/color]{health_level}
[color=#fb5607]⚠ 异常比例：[/color]{abnormal_ratio:.1f}%
[color=#8338ec]⏱ 检测时长：[/color]{duration}

[color=#4ecca3]建议：[/color]"""
        
        # 根据数据给出建议
        if abnormal_ratio < 10:
            summary += "\n心率状态良好，继续保持健康生活方式。"
        elif abnormal_ratio < 30:
            summary += "\n偶有异常波动，建议注意休息，避免过度劳累。"
        else:
            summary += "\n异常比例较高，建议咨询医生进行详细检查。"
        
        self.summary_label.text = summary

class HeartRateApp(App):
    """主应用"""
    heart_rate = NumericProperty(0)
    score = NumericProperty(0)
    status = NumericProperty(0)
    current_time = StringProperty('--:--:--')
    connection_status = StringProperty('未连接')
    is_connected = BooleanProperty(False)
    is_monitoring = BooleanProperty(False)
    
    # 统计数据
    hr_list = ListProperty([])
    score_list = ListProperty([])
    abnormal_count = NumericProperty(0)
    start_time = None
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.socket = None
        self.receive_thread = None
        self.last_data_time = 0
    
    def build(self):
        """构建UI"""
        layout = BoxLayout(orientation='vertical', padding=10, spacing=8)
        
        # 标题栏
        title_box = BoxLayout(orientation='horizontal', size_hint_y=0.06)
        title = Label(
            text='[b]心率监测系统[/b]',
            markup=True,
            font_size='20sp',
            color=(0.95, 0.95, 0.95, 1)
        )
        title_box.add_widget(title)
        
        # 连接状态
        self.status_label = Label(
            text='未连接',
            font_size='12sp',
            color=(0.6, 0.6, 0.6, 1)
        )
        title_box.add_widget(self.status_label)
        layout.add_widget(title_box)
        
        # 实时时间显示
        time_box = BoxLayout(orientation='horizontal', size_hint_y=0.05)
        time_icon = Label(text='⏱', font_size='16sp', color=(0.8, 0.8, 0.8, 1), size_hint_x=0.2)
        self.time_label = Label(
            text=datetime.now().strftime('%H:%M:%S'),
            font_size='18sp',
            color=(0.9, 0.9, 0.9, 1),
            size_hint_x=0.8
        )
        time_box.add_widget(time_icon)
        time_box.add_widget(self.time_label)
        layout.add_widget(time_box)
        
        # 心率显示区域（大字号）
        hr_box = BoxLayout(orientation='vertical', size_hint_y=0.18, spacing=3)
        with hr_box.canvas.before:
            Color(0.12, 0.12, 0.18, 1)
            self.hr_rect = Rectangle(pos=hr_box.pos, size=hr_box.size)
        hr_box.bind(pos=self.update_hr_rect, size=self.update_hr_rect)
        
        self.hr_label = Label(
            text='--',
            font_size='64sp',
            bold=True,
            color=(0.95, 0.25, 0.35, 1)
        )
        hr_box.add_widget(self.hr_label)
        
        hr_unit = Label(
            text='BPM',
            font_size='14sp',
            color=(0.7, 0.7, 0.7, 1)
        )
        hr_box.add_widget(hr_unit)
        layout.add_widget(hr_box)
        
        # 评分显示
        score_box = GridLayout(cols=2, size_hint_y=0.08, spacing=10)
        
        score_label = Label(
            text='[color=#3a86ff]⭐ 评分[/color]',
            markup=True,
            font_size='16sp',
            color=(0.8, 0.8, 0.8, 1)
        )
        score_box.add_widget(score_label)
        
        self.score_value = Label(
            text='-- 分',
            font_size='22sp',
            bold=True,
            color=(0.3, 0.7, 0.9, 1)
        )
        score_box.add_widget(self.score_value)
        layout.add_widget(score_box)
        
        # 状态显示
        status_box = GridLayout(cols=2, size_hint_y=0.08, spacing=10)
        
        status_label = Label(
            text='[color=#ffbe0b]⚠ 状态[/color]',
            markup=True,
            font_size='16sp',
            color=(0.8, 0.8, 0.8, 1)
        )
        status_box.add_widget(status_label)
        
        self.status_value = Label(
            text='正常',
            font_size='18sp',
            bold=True,
            color=(0.3, 0.9, 0.5, 1)
        )
        status_box.add_widget(self.status_value)
        layout.add_widget(status_box)
        
        # 波形图
        self.waveform = WaveformWidget()
        layout.add_widget(self.waveform)
        
        # 检测总结
        self.summary_widget = SummaryWidget()
        layout.add_widget(self.summary_widget)
        
        # 控制按钮
        btn_box = BoxLayout(orientation='horizontal', size_hint_y=0.08, spacing=10)
        
        self.connect_btn = Button(
            text='连接设备',
            font_size='16sp',
            background_color=(0.2, 0.6, 0.9, 1)
        )
        self.connect_btn.bind(on_press=self.toggle_connection)
        btn_box.add_widget(self.connect_btn)
        
        self.monitor_btn = Button(
            text='开始监测',
            font_size='16sp',
            background_color=(0.3, 0.8, 0.4, 1)
        )
        self.monitor_btn.bind(on_press=self.toggle_monitoring)
        btn_box.add_widget(self.monitor_btn)
        
        layout.add_widget(btn_box)
        
        # 定时更新时间
        Clock.schedule_interval(self.update_time, 1.0)
        Clock.schedule_interval(self.check_connection, 2.0)
        
        return layout
    
    def update_hr_rect(self, instance, value):
        self.hr_rect.pos = instance.pos
        self.hr_rect.size = instance.size
    
    def update_time(self, dt):
        """更新实时时间"""
        self.time_label.text = datetime.now().strftime('%H:%M:%S')
    
    def toggle_connection(self, instance):
        """连接/断开"""
        if self.is_connected:
            self.disconnect()
        else:
            self.connect()
    
    def connect(self):
        """连接ESP01"""
        self.status_label.text = '正在连接...'
        self.status_label.color = (0.9, 0.7, 0.2, 1)
        
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(5)
            self.socket.connect((ESP01_IP, ESP01_PORT))
            
            self.is_connected = True
            self.status_label.text = '已连接'
            self.status_label.color = (0.3, 0.9, 0.5, 1)
            self.connect_btn.text = '断开连接'
            self.connect_btn.background_color = (0.8, 0.3, 0.3, 1)
            
            self.receive_thread = threading.Thread(target=self.receive_data, daemon=True)
            self.receive_thread.start()
            self.last_data_time = time.time()
            
        except Exception as e:
            Logger.error(f'Connection error: {e}')
            self.show_popup('连接失败', f'无法连接到ESP01\n请确认WiFi已连接')
            self.status_label.text = '连接失败'
            self.status_label.color = (0.9, 0.3, 0.3, 1)
    
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
        
        self.status_label.text = '未连接'
        self.status_label.color = (0.6, 0.6, 0.6, 1)
        self.connect_btn.text = '连接设备'
        self.connect_btn.background_color = (0.2, 0.6, 0.9, 1)
        self.monitor_btn.text = '开始监测'
        self.monitor_btn.background_color = (0.3, 0.8, 0.4, 1)
    
    def receive_data(self):
        """接收数据线程"""
        buffer = ''
        while self.is_connected and self.socket:
            try:
                data = self.socket.recv(512)
                if not data:
                    Clock.schedule_once(lambda dt: self.disconnect(), 0)
                    break
                
                buffer += data.decode('utf-8', errors='ignore')
                
                while '\n' in buffer:
                    line, buffer = buffer.split('\n', 1)
                    line = line.strip()
                    
                    if line and self.is_monitoring:
                        self.parse_data(line)
                
            except socket.timeout:
                continue
            except Exception as e:
                Logger.error(f'Receive error: {e}')
                Clock.schedule_once(lambda dt: self.disconnect(), 0)
                break
    
    def parse_data(self, data_str):
        """解析数据：心率,评分,状态,时间戳"""
        try:
            parts = data_str.split(',')
            if len(parts) >= 3:
                heart_rate = int(parts[0])
                score = int(parts[1])
                status = int(parts[2])
                
                Clock.schedule_once(
                    lambda dt, hr=heart_rate, sc=score, st=status: 
                    self.update_display(hr, sc, st), 0
                )
                
                self.last_data_time = time.time()
                
        except Exception as e:
            Logger.error(f'Parse error: {e}')
    
    def update_display(self, heart_rate, score, status):
        """更新显示"""
        self.heart_rate = heart_rate
        self.score = score
        self.status = status
        
        # 更新心率
        self.hr_label.text = str(heart_rate)
        
        # 更新评分
        self.score_value.text = f'{score} 分'
        
        # 更新状态
        if status == 0:
            self.status_value.text = '正常'
            self.status_value.color = (0.3, 0.9, 0.5, 1)
        elif status == 1:
            self.status_value.text = '注意'
            self.status_value.color = (0.9, 0.7, 0.2, 1)
        else:
            self.status_value.text = '异常'
            self.status_value.color = (0.9, 0.3, 0.3, 1)
        
        # 更新波形图
        hr_list = list(self.waveform.heart_rates)
        hr_list.append(heart_rate)
        if len(hr_list) > 60:
            hr_list.pop(0)
        self.waveform.heart_rates = hr_list
        
        # 统计数据
        self.hr_list.append(heart_rate)
        self.score_list.append(score)
        if status > 0:
            self.abnormal_count += 1
        
        # 更新总结（每10个数据点更新一次）
        if len(self.hr_list) % 10 == 0:
            self.update_summary()
    
    def update_summary(self):
        """更新检测总结"""
        if len(self.hr_list) == 0:
            return
        
        hr_avg = sum(self.hr_list) / len(self.hr_list)
        hr_min = min(self.hr_list)
        hr_max = max(self.hr_list)
        score_avg = sum(self.score_list) / len(self.score_list)
        
        duration = ""
        if self.start_time:
            elapsed = time.time() - self.start_time
            mins = int(elapsed // 60)
            secs = int(elapsed % 60)
            duration = f"{mins}分{secs}秒"
        
        self.summary_widget.update_summary(
            hr_avg, hr_min, hr_max, score_avg,
            self.abnormal_count, len(self.hr_list), duration
        )
    
    def toggle_monitoring(self, instance):
        """开始/停止监测"""
        if not self.is_connected:
            self.show_popup('提示', '请先连接设备')
            return
        
        self.is_monitoring = not self.is_monitoring
        
        if self.is_monitoring:
            self.monitor_btn.text = '停止监测'
            self.monitor_btn.background_color = (0.8, 0.5, 0.2, 1)
            self.start_time = time.time()
            self.hr_list = []
            self.score_list = []
            self.abnormal_count = 0
            self.waveform.heart_rates = [0] * 60
        else:
            self.monitor_btn.text = '开始监测'
            self.monitor_btn.background_color = (0.3, 0.8, 0.4, 1)
            self.update_summary()
    
    def check_connection(self, dt):
        """检查连接"""
        if self.is_connected and self.is_monitoring:
            if time.time() - self.last_data_time > 10:
                self.disconnect()
                self.show_popup('连接断开', '与设备连接已断开')
    
    def show_popup(self, title, message):
        """显示弹窗"""
        from kivy.uix.popup import Popup
        popup = Popup(
            title=title,
            content=Label(text=message, font_size='16sp'),
            size_hint=(0.8, 0.35)
        )
        popup.open()
    
    def on_stop(self):
        self.disconnect()

if __name__ == '__main__':
    HeartRateApp().run()