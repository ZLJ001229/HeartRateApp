#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据处理模块
负责数据解析、缓存、波形处理
"""

import json
from datetime import datetime
from collections import deque

class DataProcessor:
    """数据处理类"""
    
    def __init__(self, max_cache_size=1000):
        self.max_cache_size = max_cache_size
        self.heart_rates = deque(maxlen=max_cache_size)
        self.spo2_values = deque(maxlen=max_cache_size)
        self.statuses = deque(maxlen=max_cache_size)
        self.timestamps = deque(maxlen=max_cache_size)
        
        # 波形数据（最近100个点）
        self.waveform_data = deque(maxlen=100)
        
        # 统计数据
        self.hr_min = 0
        self.hr_max = 0
        self.hr_avg = 0
        self.spo2_min = 0
        self.spo2_max = 0
        self.spo2_avg = 0
    
    def parse_data(self, data_str):
        """
        解析ESP01发送的数据
        格式: 心率,血氧,状态
        例: 78,95,0
        
        状态码:
        0 - 正常
        1 - 注意（轻微异常）
        2 - 警告（严重异常）
        """
        try:
            parts = data_str.strip().split(',')
            if len(parts) >= 3:
                heart_rate = int(parts[0])
                spo2 = int(parts[1])
                status = int(parts[2])
                
                # 数据有效性检查
                if not (40 <= heart_rate <= 200):
                    return None  # 心率超出合理范围
                if not (70 <= spo2 <= 100):
                    return None  # 血氧超出合理范围
                
                return {
                    'heart_rate': heart_rate,
                    'spo2': spo2,
                    'status': status,
                    'timestamp': datetime.now().isoformat()
                }
        except Exception as e:
            print(f"Parse error: {e}")
        
        return None
    
    def add_data(self, data):
        """添加数据到缓存"""
        if data:
            self.heart_rates.append(data['heart_rate'])
            self.spo2_values.append(data['spo2'])
            self.statuses.append(data['status'])
            self.timestamps.append(data['timestamp'])
            
            # 更新波形数据
            self.waveform_data.append(data['heart_rate'])
            
            # 更新统计
            self.update_statistics()
            
            return True
        return False
    
    def update_statistics(self):
        """更新统计数据"""
        if len(self.heart_rates) > 0:
            hr_list = list(self.heart_rates)
            self.hr_min = min(hr_list)
            self.hr_max = max(hr_list)
            self.hr_avg = sum(hr_list) / len(hr_list)
        
        if len(self.spo2_values) > 0:
            spo2_list = list(self.spo2_values)
            self.spo2_min = min(spo2_list)
            self.spo2_max = max(spo2_list)
            self.spo2_avg = sum(spo2_list) / len(spo2_list)
    
    def get_waveform_data(self):
        """获取波形数据（补齐到100个点）"""
        data = list(self.waveform_data)
        while len(data) < 100:
            data.insert(0, 0)
        return data
    
    def get_statistics(self):
        """获取统计数据"""
        return {
            'heart_rate': {
                'min': self.hr_min,
                'max': self.hr_max,
                'avg': round(self.hr_avg, 1)
            },
            'spo2': {
                'min': self.spo2_min,
                'max': self.spo2_max,
                'avg': round(self.spo2_avg, 1)
            },
            'data_count': len(self.heart_rates)
        }
    
    def get_status_text(self, status):
        """获取状态文本"""
        status_map = {
            0: ('正常', 'green'),
            1: ('注意', 'orange'),
            2: ('警告', 'red')
        }
        return status_map.get(status, ('未知', 'gray'))
    
    def save_to_file(self, filename='heart_rate_data.json'):
        """保存数据到文件"""
        try:
            data = {
                'heart_rates': list(self.heart_rates),
                'spo2_values': list(self.spo2_values),
                'statuses': list(self.statuses),
                'timestamps': list(self.timestamps)
            }
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"Save error: {e}")
            return False
    
    def load_from_file(self, filename='heart_rate_data.json'):
        """从文件加载数据"""
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            self.heart_rates.clear()
            self.spo2_values.clear()
            self.statuses.clear()
            self.timestamps.clear()
            
            for hr, spo2, status, ts in zip(
                data.get('heart_rates', []),
                data.get('spo2_values', []),
                data.get('statuses', []),
                data.get('timestamps', [])
            ):
                self.heart_rates.append(hr)
                self.spo2_values.append(spo2)
                self.statuses.append(status)
                self.timestamps.append(ts)
            
            self.update_statistics()
            return True
        except Exception as e:
            print(f"Load error: {e}")
            return False
    
    def clear(self):
        """清空所有数据"""
        self.heart_rates.clear()
        self.spo2_values.clear()
        self.statuses.clear()
        self.timestamps.clear()
        self.waveform_data.clear()
        self.hr_min = 0
        self.hr_max = 0
        self.hr_avg = 0
        self.spo2_min = 0
        self.spo2_max = 0
        self.spo2_avg = 0


class AlarmManager:
    """报警管理类"""
    
    def __init__(self):
        self.alarm_threshold_hr_high = 120  # 心率过高阈值
        self.alarm_threshold_hr_low = 50     # 心率过低阈值
        self.alarm_threshold_spo2 = 90       # 血氧过低阈值
        self.alarm_enabled = True
        self.alarm_sound = None
    
    def check_alarm(self, heart_rate, spo2, status):
        """
        检查是否需要报警
        返回: (是否报警, 报警类型, 报警消息)
        """
        if not self.alarm_enabled:
            return False, None, None
        
        # 根据状态码判断
        if status == 2:
            return True, 'critical', '严重异常！请立即检查！'
        elif status == 1:
            return True, 'warning', '心率异常，请注意观察'
        
        # 根据数值判断
        if heart_rate > self.alarm_threshold_hr_high:
            return True, 'warning', f'心率过高: {heart_rate} BPM'
        elif heart_rate < self.alarm_threshold_hr_low:
            return True, 'warning', f'心率过低: {heart_rate} BPM'
        
        if spo2 < self.alarm_threshold_spo2:
            return True, 'critical', f'血氧过低: {spo2}%'
        
        return False, None, None
    
    def set_thresholds(self, hr_high=None, hr_low=None, spo2=None):
        """设置报警阈值"""
        if hr_high is not None:
            self.alarm_threshold_hr_high = hr_high
        if hr_low is not None:
            self.alarm_threshold_hr_low = hr_low
        if spo2 is not None:
            self.alarm_threshold_spo2 = spo2
    
    def enable_alarm(self, enabled=True):
        """启用/禁用报警"""
        self.alarm_enabled = enabled