from __future__ import annotations
from dataclasses import replace
from pathlib import Path
import os
import queue
import sys
import tkinter as tk
from tkinter import messagebox
import webbrowser
import customtkinter as ctk
from PIL import Image
import qrcode
from . import __version__
from .config import Settings, VOICES, validate_relay
from .transport import Backend
from .audio import outputs
from .speech import save_azure_key

BG = '#F6F7FB'
CARD = '#FFFFFF'
INK = '#202638'
MUTED = '#7B8192'
BLUE = '#425DE8'
BORDER = '#E8EAF1'
FONT = 'Microsoft YaHei UI' if os.name == 'nt' else 'DejaVu Sans'


def font(size=13, weight='normal'):
    return ctk.CTkFont(family=FONT, size=size, weight=weight)


def button(parent, text, command, primary=False, **kw):
    return ctk.CTkButton(parent, text=text, command=command, height=38, corner_radius=10,
                        fg_color=BLUE if primary else '#F0F2FF', hover_color='#334DD3' if primary else '#E4E8FF',
                        text_color='white' if primary else BLUE, font=font(12, 'bold'), **kw)


class App(ctk.CTk):
    def __init__(self):
        ctk.set_appearance_mode('light')
        ctk.set_default_color_theme('blue')
        super().__init__()
        self.title('CloudMic Next')
        self.geometry('900x690')
        self.minsize(860, 650)
        self.configure(fg_color=BG)
        self.cfg = Settings.load()
        self.backend = Backend(self.cfg)
        self.pair_url = ''
        self.pair_expires = 0
        self.last_message = ''
        self.closing = False
        self.tray = None
        self.protocol('WM_DELETE_WINDOW', self.on_close)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self.build()
        self.refresh_devices()
        self.backend.start()
        self.after(80, self.poll)
        self.after(1000, self.countdown)
        if '--smoke-test' in sys.argv:
            self.after(3500, self.smoke_report)
        else:
            self.after(1500, self.setup_tray)

    def build(self):
        head = ctk.CTkFrame(self, fg_color='transparent')
        head.grid(row=0, column=0, sticky='ew', padx=30, pady=(26, 22))
        head.grid_columnconfigure(1, weight=1)
        mark = ctk.CTkLabel(head, text='▥', font=font(25, 'bold'), fg_color=BLUE, text_color='white', width=42, height=42, corner_radius=13)
        mark.grid(row=0, column=0, rowspan=2, padx=(0, 12))
        ctk.CTkLabel(head, text='CloudMic', font=font(23, 'bold'), text_color=INK, anchor='w').grid(row=0, column=1, sticky='w')
        ctk.CTkLabel(head, text='NEXT GENERATION   /   让文字成为声音', font=font(10), text_color=MUTED, anchor='w').grid(row=1, column=1, sticky='w')
        self.connection = ctk.CTkLabel(head, text='正在启动', font=font(11), text_color=MUTED, fg_color='#ECEEF4', corner_radius=15, width=180, height=30)
        self.connection.grid(row=0, column=2, rowspan=2, padx=(15, 12))
        button(head, '设置', self.settings_window, width=60).grid(row=0, column=3, rowspan=2)
        body = ctk.CTkFrame(self, fg_color='transparent')
        body.grid(row=1, column=0, sticky='nsew', padx=30)
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(0, weight=1)
        left = ctk.CTkFrame(body, fg_color=CARD, corner_radius=20, border_width=1, border_color=BORDER, width=260)
        left.grid(row=0, column=0, sticky='ns', padx=(0, 18))
        left.grid_propagate(False)
        left.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(left, text='连接你的手机', text_color=INK, font=font(19,'bold')).grid(row=0, column=0, padx=22, pady=(24, 3))
        ctk.CTkLabel(left, text='扫码即连，无需安装 App', text_color=MUTED, font=font(11)).grid(row=1, column=0)
        self.qr = ctk.CTkLabel(left, text='正在生成安全配对…', text_color=MUTED, font=font(11), width=204, height=204)
        self.qr.grid(row=2, column=0, padx=24, pady=(20, 12))
        self.code = ctk.CTkLabel(left, text='— — — —', text_color=BLUE, font=font(27, 'bold'))
        self.code.grid(row=3, column=0)
        self.expiry = ctk.CTkLabel(left, text='配对码有效期 10 分钟', text_color=MUTED, font=font(10))
        self.expiry.grid(row=4, column=0, pady=(2, 14))
        row = ctk.CTkFrame(left, fg_color='transparent')
        row.grid(row=5, column=0)
        button(row,'复制链接',self.copy_link,width=95).pack(side='left',padx=(0,6))
        button(row,'刷新配对',self.backend.rotate,width=95).pack(side='left')
        self.phone_count = ctk.CTkLabel(left, text='等待手机连接', text_color=MUTED, font=font(11))
        self.phone_count.grid(row=6,column=0,pady=(19,6))
        ctk.CTkLabel(left, text='手机和电脑不必连接同一 Wi-Fi\n连接中断会自动重连', text_color=MUTED,font=font(10),justify='center').grid(row=7,column=0,pady=(5,20))
        right = ctk.CTkFrame(body, fg_color=CARD, corner_radius=20, border_width=1, border_color=BORDER)
        right.grid(row=0,column=1,sticky='nsew')
        right.grid_columnconfigure(0,weight=1)
        ctk.CTkLabel(right,text='你的声音，由你选择。',text_color=INK,font=font(21,'bold'),anchor='w').grid(row=0,column=0,sticky='ew',padx=24,pady=(24,0))
        ctk.CTkLabel(right,text='选好音色和输出设备，就可以开始交流。',text_color=MUTED,font=font(11),anchor='w').grid(row=1,column=0,sticky='ew',padx=24,pady=(3,16))
        ctk.CTkLabel(right,text='音色',text_color=MUTED,font=font(11),anchor='w').grid(row=2,column=0,sticky='ew',padx=24)
        self.voice_var = tk.StringVar(value=next((k for k,v in VOICES.items() if v==self.cfg.voice),next(iter(VOICES))))
        self.voice = ctk.CTkOptionMenu(right,variable=self.voice_var,values=list(VOICES),command=lambda _:self.apply(),height=36,font=font(12),dropdown_font=font(12),fg_color='#F0F2FF',button_color='#E4E8FF',button_hover_color='#D8DFFF',text_color=INK)
        self.voice.grid(row=3,column=0,sticky='ew',padx=24,pady=(6,12))
        line=ctk.CTkFrame(right,fg_color='transparent');line.grid(row=4,column=0,sticky='ew',padx=24)
        ctk.CTkLabel(line,text='语速',font=font(11),text_color=MUTED).pack(side='left')
        self.rate_label=ctk.CTkLabel(line,text=f'{100+self.cfg.rate}%',font=font(11),text_color=MUTED);self.rate_label.pack(side='right')
        self.rate=ctk.CTkSlider(right,from_=-50,to=50,number_of_steps=20,command=self.change_rate,button_color=BLUE,progress_color=BLUE,height=16)
        self.rate.set(self.cfg.rate);self.rate.grid(row=5,column=0,sticky='ew',padx=24,pady=(1,13))
        device_line=ctk.CTkFrame(right,fg_color='transparent');device_line.grid(row=6,column=0,sticky='ew',padx=24)
        ctk.CTkLabel(device_line,text='声音输出',font=font(11),text_color=MUTED).pack(side='left')
        ctk.CTkButton(device_line,text='刷新设备',command=self.refresh_devices,width=65,height=24,fg_color='transparent',text_color=BLUE,font=font(10)).pack(side='right')
        self.device_var=tk.StringVar(value='自动选择虚拟麦克风')
        self.device=ctk.CTkOptionMenu(right,variable=self.device_var,values=['自动选择虚拟麦克风'],command=lambda _:self.apply(),height=36,font=font(11),dropdown_font=font(11),fg_color='#F0F2FF',button_color='#E4E8FF',button_hover_color='#D8DFFF',text_color=INK)
        self.device.grid(row=7,column=0,sticky='ew',padx=24,pady=(5,7))
        self.device_hint=ctk.CTkLabel(right,text='',text_color=MUTED,font=font(10),anchor='w',wraplength=480,justify='left')
        self.device_hint.grid(row=8,column=0,sticky='ew',padx=24)
        preview_line=ctk.CTkFrame(right,fg_color='transparent');preview_line.grid(row=9,column=0,sticky='ew',padx=24,pady=(8,12))
        self.preview_var=tk.BooleanVar(value=self.cfg.preview)
        ctk.CTkSwitch(preview_line,text='扬声器试听（不会发送到游戏）',variable=self.preview_var,command=self.apply,font=font(11),text_color=INK,progress_color=BLUE,width=36,height=20).pack(side='left')
        ctk.CTkLabel(right,text='先试着说一句',font=font(11),text_color=MUTED,anchor='w').grid(row=10,column=0,sticky='ew',padx=24)
        self.test_text=ctk.CTkEntry(right,placeholder_text='你好，很高兴认识你。',height=37,font=font(12),fg_color=BG,border_color=BORDER,text_color=INK)
        self.test_text.insert(0,'你好，很高兴认识你。')
        self.test_text.grid(row=11,column=0,sticky='ew',padx=24,pady=(6,10))
        self.test_text.bind('<Return>',lambda _:self.test())
        actions=ctk.CTkFrame(right,fg_color='transparent');actions.grid(row=12,column=0,sticky='ew',padx=24)
        button(actions,'试听 / 测试朗读',self.test,True,width=150).pack(side='left')
        button(actions,'停止并清空',self.backend.stop_speech,width=115).pack(side='left',padx=10)
        self.speech_status=ctk.CTkLabel(right,text='准备好了，等待你想说的话。',font=font(10),text_color=MUTED,anchor='w',wraplength=460,justify='left')
        self.speech_status.grid(row=13,column=0,sticky='ew',padx=24,pady=(12,18))
        foot=ctk.CTkFrame(self,fg_color='transparent');foot.grid(row=2,column=0,sticky='ew',padx=32,pady=(16,20))
        ctk.CTkLabel(foot,text=f'CloudMic {__version__}  ·  Keran Technology',font=font(10),text_color=MUTED).pack(side='left')
        ctk.CTkButton(foot,text='虚拟麦克风安装帮助 ↗',command=self.driver_help,fg_color='transparent',text_color=BLUE,font=font(10),height=24,width=160).pack(side='right')

    def apply(self):
        name=self.device_var.get()
        self.cfg=replace(self.cfg,voice=VOICES[self.voice_var.get()],rate=int(self.rate.get()),device='' if name=='自动选择虚拟麦克风' else name,preview=self.preview_var.get())
        self.backend.settings=self.cfg
        try:self.cfg.save()
        except OSError:self.speech_status.configure(text='设置保存失败，请检查本机用户目录权限。')

    def change_rate(self,value):
        self.rate_label.configure(text=f'{100+int(value)}%')
        self.apply()

    def test(self):
        text=self.test_text.get().strip()
        if not text:return
        if len(text)>500:self.speech_status.configure(text='每条最多 500 字');return
        self.apply();self.backend.test(text)

    def refresh_devices(self):
        try:
            devices=outputs()
            names=list(dict.fromkeys(d.name for d in devices))
            self.device.configure(values=['自动选择虚拟麦克风']+names)
            self.device_var.set(self.cfg.device if self.cfg.device in names else '自动选择虚拟麦克风')
            has_cable=any(d.cable for d in devices)
            self.device_hint.configure(text='游戏麦克风请选择 CABLE Output；云麦输出选择 CABLE Input。' if has_cable else '尚未检测到虚拟麦克风。可先打开扬声器试听，或查看安装帮助。',text_color=MUTED if has_cable else '#B27A30')
        except Exception:self.device_hint.configure(text='未能读取音频设备，请检查 Windows 音频服务。')

    def copy_link(self):
        if not self.pair_url:return
        self.clipboard_clear();self.clipboard_append(self.pair_url)
        self.expiry.configure(text='配对链接已复制')

    def countdown(self):
        if self.closing:return
        import time
        if self.pair_expires:
            left=max(0,int(self.pair_expires/1000-time.time()))
            self.expiry.configure(text=f'新设备配对剩余 {left//60:02d}:{left%60:02d}' if left else '新设备配对已过期 · 点击刷新')
        self.after(1000,self.countdown)

    def poll(self):
        if self.closing:return
        for _ in range(80):
            try:event=self.backend.events.get_nowait()
            except queue.Empty:break
            kind=event['type']
            if kind=='room':
                self.pair_url=event['url'];self.pair_expires=event['expires']
                self.code.configure(text=event['code'][:4]+' '+event['code'][4:])
                image=qrcode.make(self.pair_url).convert('RGB')
                self.qr_image=ctk.CTkImage(image,size=(204,204))
                self.qr.configure(image=self.qr_image,text='')
            elif kind=='connection':
                state=event['state'];message=event['message']
                self.connection.configure(text='安全连接已建立' if state=='on' else '连接中…' if state=='wait' else '正在重连…',text_color='#138466' if state=='on' else MUTED)
                self.phone_count.configure(text=message)
            elif kind=='peers':
                n=event['phones'];self.phone_count.configure(text=f'{n} 台手机已连接' if n else '等待手机连接')
            elif kind=='speech':
                labels={'queued':'消息已接收，正在排队','synthesizing':'正在合成语音…','playing':'正在朗读','done':'朗读完成','failed':'朗读失败','cancelled':'已停止朗读'}
                text=labels.get(event['state'],event['state'])
                if event['detail']:text+=' · '+event['detail']
                if event['state']=='playing':text+=f" · {event['ms']} ms（接收至开始播放）"
                self.speech_status.configure(text=text,text_color='#BB4C58' if event['state']=='failed' else MUTED)
            elif kind=='error':self.speech_status.configure(text=event['message'],text_color='#BB4C58')
        self.after(80,self.poll)

    def driver_help(self):
        messagebox.showinfo('首次配置虚拟麦克风','游戏或聊天软件需要虚拟音频驱动才能接收合成声音。\n\n1. 在 VB-Audio 官方页面下载 VB-CABLE。\n2. 解压完整包，以管理员身份运行安装器。\n3. 按安装器要求重启后，点击云麦“刷新设备”。\n4. 游戏内麦克风选择 CABLE Output。\n\nVB-CABLE 为第三方 donationware，许可和支持由 VB-Audio 提供。\n仅扬声器试听不需要安装驱动。',parent=self)
        webbrowser.open('https://vb-audio.com/Cable/')

    def settings_window(self):
        win=ctk.CTkToplevel(self);win.title('设置 · CloudMic');win.geometry('530x570');win.resizable(False,False);win.configure(fg_color=BG);win.transient(self)
        win.grid_columnconfigure(0,weight=1)
        ctk.CTkLabel(win,text='声音与连接',font=font(22,'bold'),text_color=INK,anchor='w').grid(row=0,column=0,sticky='ew',padx=26,pady=(24,14))
        ctk.CTkLabel(win,text='语音服务',font=font(12),text_color=MUTED,anchor='w').grid(row=1,column=0,sticky='ew',padx=26)
        engines={'自然语音 · 失败时回退本地':'auto','仅在线自然语音':'edge','仅本地语音 · 离线':'sapi','Azure Speech · 自备密钥':'azure'}
        engine=tk.StringVar(value=next(k for k,v in engines.items() if v==self.cfg.engine))
        ctk.CTkOptionMenu(win,variable=engine,values=list(engines),font=font(12),height=36).grid(row=2,column=0,sticky='ew',padx=26,pady=(6,14))
        volume=ctk.CTkSlider(win,from_=0,to=100,number_of_steps=100);volume.set(self.cfg.volume*100)
        ctk.CTkLabel(win,text='音量（0–100%）',font=font(12),text_color=MUTED,anchor='w').grid(row=3,column=0,sticky='ew',padx=26)
        volume.grid(row=4,column=0,sticky='ew',padx=26,pady=(6,14))
        ctk.CTkLabel(win,text='HTTPS 中转地址（更改后需重新配对）',font=font(12),text_color=MUTED,anchor='w').grid(row=5,column=0,sticky='ew',padx=26)
        relay=ctk.CTkEntry(win,height=36,font=font(12));relay.insert(0,self.cfg.relay);relay.grid(row=6,column=0,sticky='ew',padx=26,pady=(6,14))
        ctk.CTkLabel(win,text='Azure 区域 / 密钥（选填，仅保存在 Windows 凭据管理器）',font=font(11),text_color=MUTED,anchor='w').grid(row=7,column=0,sticky='ew',padx=26)
        region=ctk.CTkEntry(win,height=34,font=font(12));region.insert(0,self.cfg.azure_region);region.grid(row=8,column=0,sticky='ew',padx=26,pady=(6,7))
        key=ctk.CTkEntry(win,height=34,font=font(12),show='•',placeholder_text='留空保留已存密钥；输入 - 删除密钥');key.grid(row=9,column=0,sticky='ew',padx=26,pady=(0,10))
        ctk.CTkLabel(win,text='在线文字会发送到选定语音服务。\n默认在线服务非商业 SLA，网络异常时可使用本地语音。',font=font(10),text_color=MUTED,justify='left',anchor='w').grid(row=10,column=0,sticky='ew',padx=26,pady=(0,14))
        def save():
            try:
                address=validate_relay(relay.get())
                import re
                if not re.fullmatch(r'[a-z0-9-]{2,40}',region.get().strip()):raise ValueError('Azure 区域格式无效')
                if key.get().strip():save_azure_key('' if key.get().strip()=='-' else key.get().strip())
                changed=address!=self.cfg.relay
                self.cfg=replace(self.cfg,relay=address,engine=engines[engine.get()],volume=volume.get()/100,azure_region=region.get().strip())
                self.cfg.save();self.backend.settings=self.cfg
                if changed:self.backend.rotate()
                win.destroy()
            except Exception as exc:messagebox.showerror('无法保存',str(exc),parent=win)
        button(win,'保存设置',save,True).grid(row=11,column=0,sticky='ew',padx=26)
        win.after(50,win.grab_set)

    def smoke_report(self):
        import json
        from PIL import ImageGrab
        report=Path(sys.argv[sys.argv.index('--smoke-test')+1])
        self.update_idletasks()
        if os.name=='nt':
            box=(self.winfo_rootx(),self.winfo_rooty(),self.winfo_rootx()+self.winfo_width(),self.winfo_rooty()+self.winfo_height())
            ImageGrab.grab(bbox=box).save(report.with_suffix('.png'))
        report.write_text(json.dumps({'ok':self.winfo_width()>=860,'version':__version__,
            'width':self.winfo_width(),'height':self.winfo_height(),'audio_devices':len(outputs()),
            'ui':'packaged application startup, no physical audio playback tested'},ensure_ascii=False),encoding='utf-8')
        self.quit_app()

    def setup_tray(self):
        if os.name!='nt' or self.closing:return
        try:
            import pystray
            from PIL import ImageDraw
            image=Image.new('RGB',(64,64),BLUE);d=ImageDraw.Draw(image)
            for x,top,bottom in [(18,26,40),(32,15,50),(46,22,44)]:d.line((x,top,x,bottom),fill='white',width=5)
            self.tray=pystray.Icon('CloudMic',image,'CloudMic Next',menu=pystray.Menu(
                pystray.MenuItem('打开云麦',lambda:self.after(0,self.show),default=True),
                pystray.MenuItem('停止朗读',lambda:self.backend.stop_speech()),
                pystray.MenuItem('退出',lambda:self.after(0,self.quit_app))))
            self.tray.run_detached()
        except Exception:self.tray=None

    def show(self):self.deiconify();self.lift();self.focus_force()

    def on_close(self):
        if self.tray:self.withdraw()
        else:self.quit_app()

    def quit_app(self):
        self.closing=True;self.backend.close()
        if self.tray:self.tray.stop()
        self.destroy()


def main():
    # A portable exe still stores preferences in the user's profile, never beside the exe.
    app=App()
    app.mainloop()
