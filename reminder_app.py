import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import json
import os
import time
import threading
import sys
from datetime import datetime, date
import csv
import gc
import psutil

# 配置文件管理类
class ConfigManager:
    def __init__(self, config_file="config.json"):
        self.config_file = config_file
        self.default_config = {
            "interval": 30,
            "message": "该休息一下了！",
            "sound_enabled": True,
            "auto_start": False,
            "enabled": False,
            "message_history": [],
            "reminder_history": [],  # 新增：提醒历史记录
            "statistics": {  # 新增：统计数据
                "total_reminders": 0,
                "today_reminders": 0,
                "last_reset_date": str(date.today()),
                "total_runtime_seconds": 0,
                "session_start_time": None,
                "total_timer_seconds": 0,  # 新增：累计计时总时间（秒）
                "today_timer_seconds": 0,   # 新增：今日计时总时间（秒）
                "timer_start_time": None    # 新增：当前计时开始时间
            }
        }
    
    def load(self):
        """加载配置"""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    # 合并默认配置，确保所有字段都存在
                    merged_config = {**self.default_config, **config}
                    
                    # 确保统计数据完整
                    if "statistics" not in merged_config:
                        merged_config["statistics"] = self.default_config["statistics"].copy()
                    else:
                        merged_config["statistics"] = {
                            **self.default_config["statistics"],
                            **merged_config["statistics"]
                        }
                    
                    # 检查日期是否需要重置今日统计
                    self._check_daily_reset(merged_config)
                    
                    return merged_config
            except Exception as e:
                print(f"加载配置失败: {e}")
                return self.default_config.copy()
        return self.default_config.copy()
    
    def _check_daily_reset(self, config):
        """检查并重置每日统计"""
        today = str(date.today())
        if config["statistics"].get("last_reset_date") != today:
            config["statistics"]["today_reminders"] = 0
            config["statistics"]["today_timer_seconds"] = 0
            config["statistics"]["last_reset_date"] = today
    
    def save(self, config):
        """保存配置"""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=4, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"保存配置失败: {e}")
            return False

# 提醒窗口类
class ReminderWindow:
    def __init__(self, message, callback):
        self.message = message
        self.callback = callback
        
        # 创建顶层窗口
        self.window = tk.Toplevel()
        self.window.title("定时提醒")
        self.window.attributes('-topmost', True)
        
        # 窗口大小和位置
        window_width = 400
        window_height = 250
        screen_width = self.window.winfo_screenwidth()
        screen_height = self.window.winfo_screenheight()
        x = (screen_width - window_width) // 2
        y = (screen_height - window_height) // 2
        self.window.geometry(f"{window_width}x{window_height}+{x}+{y}")
        
        # 设置窗口样式
        self.window.configure(bg="white")
        self.window.resizable(False, False)
        
        # 创建界面
        self._create_widgets()
        
        # 窗口关闭事件
        self.window.protocol("WM_DELETE_WINDOW", self.on_know)
        
        # 播放提示音（可选）
        try:
            self.window.bell()
        except:
            pass
    
    def _create_widgets(self):
        """创建窗口控件"""
        # 创建主框架
        main_frame = tk.Frame(self.window, bg="white", padx=20, pady=20)
        main_frame.pack(fill="both", expand=True, padx=5, pady=5)
        
        # 标题
        title = tk.Label(main_frame, text="🔔 时间到了!", 
                        font=("微软雅黑", 16, "bold"), 
                        bg="white", fg="#333")
        title.pack(pady=(0, 10))
        
        # 消息内容
        msg_label = tk.Label(main_frame, text=self.message,
                            font=("微软雅黑", 12),
                            bg="white", fg="#666",
                            wraplength=300, justify="center")
        msg_label.pack(pady=10)
        
        # 按钮框架
        btn_frame = tk.Frame(main_frame, bg="white")
        btn_frame.pack(pady=15)
        
        # 稍后提醒按钮
        snooze_btn = tk.Button(btn_frame, text="稍后提醒(5分钟)", 
                              font=("微软雅黑", 10),
                              bg="#f3f4f6", fg="#333",
                              width=15, height=1,
                              relief="flat", cursor="hand2",
                              command=self.on_snooze)
        snooze_btn.pack(side="left", padx=5)
        
        # 我知道了按钮
        know_btn = tk.Button(btn_frame, text="我知道了", 
                            font=("微软雅黑", 10, "bold"),
                            bg="#3b82f6", fg="white",
                            width=15, height=1,
                            relief="flat", cursor="hand2",
                            command=self.on_know)
        know_btn.pack(side="left", padx=5)
        
        # 绑定快捷键
        self.window.bind('<Return>', lambda e: self.on_know())
        self.window.bind('<Escape>', lambda e: self.on_snooze())
    
    def on_snooze(self):
        """稍后提醒"""
        self.callback(5, "snooze")  # 5分钟后提醒，响应方式为snooze
        self.window.destroy()
    
    def on_know(self):
        """我知道了"""
        self.callback(0, "dismissed")  # 不再提醒，响应方式为dismissed
        self.window.destroy()

# 历史记录窗口类
class HistoryWindow:
    def __init__(self, parent, reminder_history, config_manager):
        self.parent = parent
        self.reminder_history = reminder_history
        self.config_manager = config_manager
        
        # 创建窗口
        self.window = tk.Toplevel(parent)
        self.window.title("提醒历史记录")
        self.window.geometry("800x600")
        
        # 创建界面
        self._create_widgets()
        
        # 加载数据
        self.refresh_data()
    
    def _create_widgets(self):
        """创建控件"""
        # 顶部工具栏
        toolbar = tk.Frame(self.window, bg="#f9fafb", padx=10, pady=10)
        toolbar.pack(fill="x")
        
        tk.Label(toolbar, text="📊 提醒历史记录",
                font=("微软雅黑", 14, "bold"),
                bg="#f9fafb").pack(side="left")
        
        # 导出按钮
        export_btn = tk.Button(toolbar, text="导出为CSV",
                              font=("微软雅黑", 9),
                              bg="#10b981", fg="white",
                              relief="flat", cursor="hand2",
                              command=self.export_to_csv)
        export_btn.pack(side="right", padx=5)
        
        # 清空按钮
        clear_btn = tk.Button(toolbar, text="清空历史",
                             font=("微软雅黑", 9),
                             bg="#ef4444", fg="white",
                             relief="flat", cursor="hand2",
                             command=self.clear_history)
        clear_btn.pack(side="right", padx=5)
        
        # 创建表格框架
        table_frame = tk.Frame(self.window)
        table_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        # 创建滚动条
        scrollbar_y = ttk.Scrollbar(table_frame, orient="vertical")
        scrollbar_x = ttk.Scrollbar(table_frame, orient="horizontal")
        
        # 创建Treeview
        self.tree = ttk.Treeview(table_frame,
                                 columns=("time", "message", "response", "response_time"),
                                 show="headings",
                                 yscrollcommand=scrollbar_y.set,
                                 xscrollcommand=scrollbar_x.set)
        
        # 配置滚动条
        scrollbar_y.config(command=self.tree.yview)
        scrollbar_x.config(command=self.tree.xview)
        
        # 设置列标题
        self.tree.heading("time", text="提醒时间")
        self.tree.heading("message", text="提醒内容")
        self.tree.heading("response", text="响应方式")
        self.tree.heading("response_time", text="响应时间")
        
        # 设置列宽
        self.tree.column("time", width=150)
        self.tree.column("message", width=300)
        self.tree.column("response", width=100)
        self.tree.column("response_time", width=150)
        
        # 布局
        self.tree.grid(row=0, column=0, sticky="nsew")
        scrollbar_y.grid(row=0, column=1, sticky="ns")
        scrollbar_x.grid(row=1, column=0, sticky="ew")
        
        table_frame.grid_rowconfigure(0, weight=1)
        table_frame.grid_columnconfigure(0, weight=1)
        
        # 统计信息
        stats_frame = tk.Frame(self.window, bg="#f0f9ff", padx=10, pady=10)
        stats_frame.pack(fill="x", padx=10, pady=(0, 10))
        
        self.stats_label = tk.Label(stats_frame, text="",
                                    font=("微软雅黑", 10),
                                    bg="#f0f9ff", fg="#1e40af",
                                    justify="left")
        self.stats_label.pack(anchor="w")
    
    def refresh_data(self):
        """刷新数据"""
        # 清空现有数据
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        # 插入数据（倒序显示，最新的在前面）
        for record in reversed(self.reminder_history):
            response_text = "稍后提醒" if record["response"] == "snooze" else "已确认"
            self.tree.insert("", "end", values=(
                record["trigger_time"],
                record["message"],
                response_text,
                record["response_time"]
            ))
        
        # 更新统计信息
        total = len(self.reminder_history)
        snoozed = sum(1 for r in self.reminder_history if r["response"] == "snooze")
        dismissed = sum(1 for r in self.reminder_history if r["response"] == "dismissed")
        
        stats_text = f"总计: {total} 次提醒  |  已确认: {dismissed} 次  |  稍后提醒: {snoozed} 次"
        self.stats_label.config(text=stats_text)
    
    def export_to_csv(self):
        """导出为CSV文件"""
        if not self.reminder_history:
            messagebox.showinfo("提示", "没有可导出的数据")
            return
        
        file_path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV文件", "*.csv"), ("所有文件", "*.*")],
            initialfile=f"提醒历史_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        )
        
        if file_path:
            try:
                with open(file_path, 'w', newline='', encoding='utf-8-sig') as f:
                    writer = csv.writer(f)
                    writer.writerow(["提醒时间", "提醒内容", "响应方式", "响应时间"])
                    
                    for record in self.reminder_history:
                        response_text = "稍后提醒" if record["response"] == "snooze" else "已确认"
                        writer.writerow([
                            record["trigger_time"],
                            record["message"],
                            response_text,
                            record["response_time"]
                        ])
                
                messagebox.showinfo("成功", f"历史记录已导出到:\n{file_path}")
            except Exception as e:
                messagebox.showerror("错误", f"导出失败: {e}")
    
    def clear_history(self):
        """清空历史记录"""
        if messagebox.askyesno("确认", "确定要清空所有历史记录吗？此操作不可恢复。"):
            self.reminder_history.clear()
            self.refresh_data()
            messagebox.showinfo("成功", "历史记录已清空")

# 主应用类
class MainApp:
    def __init__(self):
        self.config_manager = ConfigManager()
        self.config = self.config_manager.load()
        
        self.root = None
        self.running = False
        self.timer_thread = None
        self.next_trigger_time = 0
        self.snooze_time = 0
        self.update_countdown_id = None
        self.memory_monitor_id = None
        self.runtime_update_id = None
        
        # 记录会话开始时间
        if self.config["statistics"]["session_start_time"] is None:
            self.config["statistics"]["session_start_time"] = time.time()
        
        self._create_main_window()
    
    def _create_main_window(self):
        """创建主窗口"""
        self.root = tk.Tk()
        self.root.title("定时提醒工具")
        
        # 初始窗口大小
        window_width = 600
        window_height = 750
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        x = (screen_width - window_width) // 2
        y = (screen_height - window_height) // 2
        self.root.geometry(f"{window_width}x{window_height}+{x}+{y}")
        
        # 设置最小窗口尺寸（响应式布局）
        self.root.minsize(500, 500)
        
        # 设置窗口图标（可选）
        try:
            self.root.iconbitmap("icon.ico")
        except:
            pass
        
        # 创建界面
        self._create_widgets()
        
        # 窗口关闭事件
        self.root.protocol("WM_DELETE_WINDOW", self.minimize_to_taskbar)
        
        # 启动内存监控
        self.monitor_memory()
        
        # 启动运行时长更新
        self.update_runtime()
    
    def _create_widgets(self):
        """创建界面控件（响应式布局）"""
        # 主框架
        main_frame = tk.Frame(self.root, bg="#f9fafb", padx=20, pady=20)
        main_frame.pack(fill="both", expand=True)
        
        # 配置行列权重以支持响应式
        main_frame.grid_rowconfigure(2, weight=1)
        main_frame.grid_columnconfigure(0, weight=1)
        
        # 标题
        title_label = tk.Label(main_frame, text="⏰ 定时提醒工具",
                              font=("微软雅黑", 18, "bold"),
                              bg="#f9fafb", fg="#1f2937")
        title_label.grid(row=0, column=0, pady=(0, 15), sticky="w")
        
        # 统计信息框架
        stats_frame = tk.LabelFrame(main_frame, text="📊 统计信息",
                                    font=("微软雅黑", 11, "bold"),
                                    bg="#f0f9ff", fg="#1e40af",
                                    padx=15, pady=10)
        stats_frame.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        
        self.stats_var = tk.StringVar()
        stats_label = tk.Label(stats_frame, textvariable=self.stats_var,
                              font=("微软雅黑", 10),
                              bg="#f0f9ff", fg="#1e3a8a",
                              justify="left")
        stats_label.pack(anchor="w")
        self.update_statistics_display()
        
        # 查看历史按钮
        history_btn = tk.Button(stats_frame, text="查看历史记录",
                               font=("微软雅黑", 9),
                               bg="#3b82f6", fg="white",
                               relief="flat", cursor="hand2",
                               command=self.show_history)
        history_btn.pack(anchor="e", pady=(5, 0))
        
        # 控制区域
        self.control_frame = tk.LabelFrame(main_frame, text="设置",
                                          font=("微软雅黑", 11, "bold"),
                                          bg="white", fg="#374151",
                                          padx=15, pady=15)
        self.control_frame.grid(row=2, column=0, sticky="nsew", pady=(0, 10))
        
        # 配置控制框架的行列权重
        self.control_frame.grid_rowconfigure(3, weight=1)
        self.control_frame.grid_columnconfigure(0, weight=1)
        
        # 间隔时间设置
        interval_frame = tk.Frame(self.control_frame, bg="white")
        interval_frame.grid(row=0, column=0, sticky="ew", pady=5)
        
        tk.Label(interval_frame, text="间隔时间(分钟):",
                font=("微软雅黑", 10),
                bg="white", fg="#4b5563").pack(side="left")
        
        self.interval_var = tk.StringVar(value=str(self.config["interval"]))
        interval_entry = tk.Entry(interval_frame, textvariable=self.interval_var,
                                 font=("微软雅黑", 10),
                                 width=10, relief="solid", bd=1)
        interval_entry.pack(side="left", padx=10)
        
        # 快速预设按钮
        preset_frame = tk.Frame(self.control_frame, bg="white")
        preset_frame.grid(row=1, column=0, sticky="ew", pady=10)
        
        tk.Label(preset_frame, text="快速设置:",
                font=("微软雅黑", 10),
                bg="white", fg="#4b5563").pack(side="left", padx=(0, 10))
        
        # 创建30、45、60分钟预设按钮
        for minutes in [30, 45, 60]:
            preset_btn = tk.Button(preset_frame, 
                                  text=f"{minutes}分钟",
                                  font=("微软雅黑", 9),
                                  bg="#e0e7ff", fg="#3730a3",
                                  width=10, height=1,
                                  relief="flat", cursor="hand2",
                                  command=lambda m=minutes: self.set_preset_time(m))
            preset_btn.pack(side="left", padx=3)
        
        # 提醒消息设置
        message_frame = tk.Frame(self.control_frame, bg="white")
        message_frame.grid(row=2, column=0, sticky="ew", pady=5)
        
        tk.Label(message_frame, text="提醒内容:",
                font=("微软雅黑", 10),
                bg="white", fg="#4b5563").pack(side="left")
        
        self.message_var = tk.StringVar(value=self.config["message"])
        message_entry = tk.Entry(message_frame, textvariable=self.message_var,
                                font=("微软雅黑", 10),
                                relief="solid", bd=1)
        message_entry.pack(side="left", fill="x", expand=True, padx=10)
        
        # 保存按钮
        save_btn = tk.Button(self.control_frame, text="保存设置",
                            font=("微软雅黑", 10),
                            bg="#10b981", fg="white",
                            width=15, height=1,
                            relief="flat", cursor="hand2",
                            command=self.save_config)
        save_btn.grid(row=3, column=0, pady=(10, 0))
        
        # 控制按钮区域
        btn_frame = tk.Frame(main_frame, bg="#f9fafb")
        btn_frame.grid(row=3, column=0, sticky="ew", pady=10)
        btn_frame.grid_columnconfigure(0, weight=1)
        btn_frame.grid_columnconfigure(1, weight=1)
        
        self.start_btn = tk.Button(btn_frame, text="开始计时",
                                   font=("微软雅黑", 11, "bold"),
                                   bg="#3b82f6", fg="white",
                                   height=2,
                                   relief="flat", cursor="hand2",
                                   command=self.start_timer)
        self.start_btn.grid(row=0, column=0, padx=5, sticky="ew")
        
        self.stop_btn = tk.Button(btn_frame, text="停止计时",
                                 font=("微软雅黑", 11, "bold"),
                                 bg="#ef4444", fg="white",
                                 height=2,
                                 relief="flat", cursor="hand2",
                                 state="disabled",
                                 command=self.stop_timer)
        self.stop_btn.grid(row=0, column=1, padx=5, sticky="ew")
        
        # 倒计时显示区域（带进度条）
        countdown_frame = tk.LabelFrame(main_frame, text="倒计时",
                                       font=("微软雅黑", 11, "bold"),
                                       bg="#fee2e2", fg="#991b1b",
                                       padx=15, pady=15)
        countdown_frame.grid(row=4, column=0, sticky="ew", pady=10)
        
        self.countdown_var = tk.StringVar(value="")
        self.countdown_label = tk.Label(countdown_frame, textvariable=self.countdown_var,
                                       font=("Arial", 28, "bold"),
                                       fg="#dc2626",
                                       bg="#fee2e2")
        self.countdown_label.pack(pady=(0, 10))
        
        # 进度条
        self.progress_var = tk.DoubleVar(value=0)
        self.progress_bar = ttk.Progressbar(countdown_frame, 
                                           variable=self.progress_var,
                                           maximum=100,
                                           mode='determinate',
                                           length=400)
        self.progress_bar.pack(fill="x", pady=(0, 5))
        
        # 状态显示
        self.status_var = tk.StringVar()
        self.status_label = tk.Label(countdown_frame, textvariable=self.status_var,
                                     font=("微软雅黑", 10),
                                     bg="#fee2e2", fg="#991b1b")
        self.status_label.pack()
        
        # 底部按钮
        bottom_frame = tk.Frame(main_frame, bg="#f9fafb")
        bottom_frame.grid(row=5, column=0, sticky="ew", pady=(5, 0))
        
        minimize_btn = tk.Button(bottom_frame, text="最小化到任务栏",
                                font=("微软雅黑", 9),
                                bg="#6b7280", fg="white",
                                width=15, height=1,
                                relief="flat", cursor="hand2",
                                command=self.minimize_to_taskbar)
        minimize_btn.pack(side="left", padx=5)
        
        exit_btn = tk.Button(bottom_frame, text="退出程序",
                            font=("微软雅黑", 9),
                            bg="#dc2626", fg="white",
                            width=15, height=1,
                            relief="flat", cursor="hand2",
                            command=self.exit_app)
        exit_btn.pack(side="right", padx=5)
        
        # 初始化显示
        self.update_button_state()
        self.update_status()
    
    def update_statistics_display(self):
        """更新统计信息显示"""
        stats = self.config["statistics"]
        
        # 计算运行时长
        runtime_seconds = stats["total_runtime_seconds"]
        if stats["session_start_time"]:
            runtime_seconds += time.time() - stats["session_start_time"]
        
        runtime_hours = int(runtime_seconds // 3600)
        runtime_minutes = int((runtime_seconds % 3600) // 60)
        
        # 计算计时总时间
        timer_seconds = stats["total_timer_seconds"]
        if stats["timer_start_time"] and self.running:
            timer_seconds += time.time() - stats["timer_start_time"]
        
        timer_hours = int(timer_seconds // 3600)
        timer_minutes = int((timer_seconds % 3600) // 60)
        
        stats_text = (
            f"今日提醒: {stats['today_reminders']} 次  |  "
            f"总提醒: {stats['total_reminders']} 次\n"
            f"今日计时: {timer_hours}小时{timer_minutes}分钟  |  "
            f"累计计时: {timer_hours}小时{timer_minutes}分钟\n"
            f"程序运行: {runtime_hours}小时{runtime_minutes}分钟"
        )
        self.stats_var.set(stats_text)
    
    def update_runtime(self):
        """更新运行时长"""
        if self.root:
            self.update_statistics_display()
            self.runtime_update_id = self.root.after(60000, self.update_runtime)  # 每分钟更新
    
    def show_history(self):
        """显示历史记录窗口"""
        HistoryWindow(self.root, self.config.get("reminder_history", []), self.config_manager)
    
    def save_config(self):
        """保存配置"""
        try:
            interval = int(self.interval_var.get())
            if interval <= 0:
                raise ValueError("间隔时间必须大于0")
            
            self.config["interval"] = interval
            self.config["message"] = self.message_var.get().strip() or "该休息一下了！"
            
            if self.config_manager.save(self.config):
                messagebox.showinfo("成功", "配置已保存！")
            else:
                messagebox.showerror("错误", "保存配置失败")
        except ValueError as e:
            messagebox.showerror("错误", f"请输入有效的间隔时间：{e}")
    
    def set_preset_time(self, minutes):
        """设置预设时间并自动重启计时器"""
        # 填入预设时间
        self.interval_var.set(str(minutes))
        
        # 更新配置
        self.config["interval"] = minutes
        
        # 如果提醒内容为空，使用默认内容
        if not self.message_var.get().strip():
            self.message_var.set("该休息一下了！")
        
        self.config["message"] = self.message_var.get().strip()
        self.config_manager.save(self.config)
        
        # 如果正在运行，先停止
        if self.running:
            self.stop_timer()
        
        # 自动启动计时器
        self.start_timer()
        
        # 提示用户
        messagebox.showinfo("提示", f"已设置{minutes}分钟定时提醒，计时已开始")
    
    def update_button_state(self):
        """更新按钮状态"""
        if self.running:
            self.start_btn.config(state="disabled")
            self.stop_btn.config(state="normal")
        else:
            self.start_btn.config(state="normal")
            self.stop_btn.config(state="disabled")
    
    def update_status(self):
        """更新状态显示"""
        if self.running:
            self.status_var.set(f"✓ 计时器运行中 - 间隔：{self.config['interval']}分钟")
        else:
            self.status_var.set("✗ 计时器已停止")
    
    def update_countdown(self):
        """更新倒计时显示和进度条"""
        if not self.running:
            self.countdown_var.set("")
            self.progress_var.set(0)
            return
        
        total_seconds = self.config["interval"] * 60
        remaining = self.next_trigger_time - time.time()
        
        if remaining <= 0:
            self.countdown_var.set("00:00:00")
            self.progress_var.set(100)
        else:
            hours = int(remaining // 3600)
            minutes = int((remaining % 3600) // 60)
            seconds = int(remaining % 60)
            self.countdown_var.set(f"{hours:02d}:{minutes:02d}:{seconds:02d}")
            
            # 更新进度条
            elapsed = total_seconds - remaining
            progress = (elapsed / total_seconds) * 100
            self.progress_var.set(progress)
        
        # 继续更新
                # 继续更新
        if self.running and self.root:
            self.update_countdown_id = self.root.after(1000, self.update_countdown)
    
    def start_timer(self):
        """启动定时器"""
        if self.running:
            return
        
        try:
            # 验证并保存配置
            interval = int(self.interval_var.get())
            if interval <= 0:
                raise ValueError("间隔时间必须大于0")
            
            self.config["interval"] = interval
            self.config["message"] = self.message_var.get().strip() or "该休息一下了！"
            self.config_manager.save(self.config)
            
            self.running = True
            self.next_trigger_time = time.time() + self.config["interval"] * 60
            self.snooze_time = 0
            
            # 记录计时开始时间（用于统计完整计时段落）
            self.config["statistics"]["timer_start_time"] = time.time()
            
            self.timer_thread = threading.Thread(target=self.timer_loop, daemon=True)
            self.timer_thread.start()
            
            # 更新UI
            self.update_button_state()
            self.update_status()
            self.update_countdown()
            
            print(f"定时器已启动，间隔：{self.config['interval']}分钟")
        except ValueError as e:
            messagebox.showerror("错误", f"请输入有效的间隔时间：{e}")
    
    def stop_timer(self):
        """停止定时器"""
        self.running = False
        self.snooze_time = 0
        
        # 停止倒计时更新
        if self.update_countdown_id and self.root:
            self.root.after_cancel(self.update_countdown_id)
            self.update_countdown_id = None
        
        # 更新UI
        self.update_button_state()
        self.update_status()
        self.countdown_var.set("")
        self.progress_var.set(0)
        
        print("定时器已停止")
    
    def timer_loop(self):
        """定时器循环"""
        while self.running:
            current_time = time.time()
            
            # 检查是否需要触发提醒
            if current_time >= self.next_trigger_time:
                self.show_reminder()
                self.next_trigger_time = current_time + self.config["interval"] * 60
            
            time.sleep(1)
    
    def show_reminder(self):
        """显示提醒窗口"""
        if self.root:
            self.root.after(0, self._create_reminder_window)
    
    def _create_reminder_window(self):
        """在主线程中创建提醒窗口"""
        try:
            ReminderWindow(self.config["message"], self.on_reminder_close)
        except Exception as e:
            print(f"创建提醒窗口失败: {e}")
    
    def on_reminder_close(self, snooze_minutes, response_type):
        """提醒窗口关闭回调"""
        # 记录提醒历史
        reminder_record = {
            "trigger_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "message": self.config["message"],
            "response": response_type,
            "response_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        if "reminder_history" not in self.config:
            self.config["reminder_history"] = []
        
        self.config["reminder_history"].append(reminder_record)
        
        # 更新统计数据
        self.config["statistics"]["total_reminders"] += 1
        self.config["statistics"]["today_reminders"] += 1
        
        # 统计完整的计时段落（只有在确认休息时才统计）
        if response_type == "dismissed" and self.config["statistics"]["timer_start_time"]:
            timer_duration = time.time() - self.config["statistics"]["timer_start_time"]
            
            # 累加到总统计
            self.config["statistics"]["total_timer_seconds"] += timer_duration
            self.config["statistics"]["today_timer_seconds"] += timer_duration
            
            # 重置计时开始时间
            self.config["statistics"]["timer_start_time"] = None
            
            # 显示统计信息
            minutes = int(timer_duration // 60)
            seconds = int(timer_duration % 60)
            print(f"本次计时完成：{minutes}分{seconds}秒")
        
        # 保存配置
        self.config_manager.save(self.config)
        
        # 更新统计显示
        self.update_statistics_display()
        
        if snooze_minutes > 0:
            # 稍后提醒：5分钟后再次提醒，但不停止计时
            self.snooze_time = time.time() + snooze_minutes * 60
            print(f"稍后提醒：{snooze_minutes}分钟后")
        else:
            # 我知道了：停止计时，需要手动重新启动
            self.stop_timer()
            print("提醒已关闭，计时已停止")
    
    def monitor_memory(self):
        """监控内存使用"""
        try:
            process = psutil.Process(os.getpid())
            memory_info = process.memory_info()
            memory_mb = memory_info.rss / 1024 / 1024
            
            # 如果内存使用超过100MB，执行垃圾回收
            if memory_mb > 100:
                gc.collect()
                print(f"内存优化：当前使用 {memory_mb:.2f} MB，已执行垃圾回收")
        except Exception as e:
            print(f"内存监控错误: {e}")
        
        # 每10分钟检查一次
        if self.root:
            self.memory_monitor_id = self.root.after(600000, self.monitor_memory)
    
    def minimize_to_taskbar(self):
        """最小化到任务栏"""
        if self.root:
            self.root.iconify()
    
    def exit_app(self):
        """完全退出应用"""
        if messagebox.askyesno("确认退出", "确定要退出定时提醒工具吗?\n\n提醒功能将停止工作。"):
            # 保存运行时长
            if self.config["statistics"]["session_start_time"]:
                session_time = time.time() - self.config["statistics"]["session_start_time"]
                self.config["statistics"]["total_runtime_seconds"] += session_time
                self.config["statistics"]["session_start_time"] = None
            
            # 保存配置
            self.config_manager.save(self.config)
            
            # 停止定时器
            self.stop_timer()
            
            # 取消所有定时任务
            if self.update_countdown_id:
                self.root.after_cancel(self.update_countdown_id)
            if self.memory_monitor_id:
                self.root.after_cancel(self.memory_monitor_id)
            if self.runtime_update_id:
                self.root.after_cancel(self.runtime_update_id)
            
            # 清理资源
            gc.collect()
            
            # 退出程序
            if self.root:
                self.root.quit()
                self.root.destroy()
            sys.exit(0)
    
    def run(self):
        """运行应用"""
        if self.root:
            self.root.mainloop()

# 程序入口
if __name__ == "__main__":
    app = MainApp()
    app.run()