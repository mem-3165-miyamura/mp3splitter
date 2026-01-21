import os
import sys
import tkinter as tk
from tkinter import filedialog, messagebox
from pydub import AudioSegment, silence
from mutagen.mp3 import MP3
from mutagen.id3 import ID3

class Mp3SplitterApp:
    def __init__(self, root):
        self.root = root
        self.root.title("MP3 アルバム一括分割ツール")
        self.root.geometry("600x750")
        
        self.audio = None
        self.file_path = ""
        self.album_name = "Unknown_Album"

        # --- UIレイアウト ---
        # 1. ファイル選択
        frame_top = tk.Frame(root)
        frame_top.pack(pady=10, fill=tk.X, padx=20)
        
        tk.Button(frame_top, text="MP3ファイルを選択", command=self.load_file, bg="#e1e1e1").pack(side=tk.LEFT)
        self.label_file = tk.Label(frame_top, text="ファイルが未選択です", fg="gray", padx=10)
        self.label_file.pack(side=tk.LEFT)

        # 2. 解析ボタン
        tk.Button(root, text="Step 1: 無音部分を解析して切れ目を提案", 
                  command=self.analyze_silence, bg="#d4edda", height=2).pack(pady=10, fill=tk.X, padx=20)

        # 3. エディタエリア
        lbl_hint = tk.Label(root, text="【切れ目リスト】\n時間は自動入力されます。その横に曲名をコピペしてください。\n例: 03:10 曲名タイトル", justify=tk.LEFT, fg="#555")
        lbl_hint.pack(pady=5)
        
        self.text_area = tk.Text(root, width=60, height=20, font=("Consolas", 10))
        self.text_area.pack(pady=5, padx=20)

        # 4. 実行ボタン
        tk.Button(root, text="Step 2: この内容で分割実行", 
                  command=self.split_execute, bg="#cce5ff", height=2, font=("", 10, "bold")).pack(pady=20, fill=tk.X, padx=20)

    def load_file(self):
        self.file_path = filedialog.askopenfilename(filetypes=[("MP3 files", "*.mp3")])
        if not self.file_path: return

        # 実行ファイルと同じ場所にffmpeg.exeがあるか確認
        self.setup_ffmpeg()

        # ファイル名からアルバム名取得
        base_name = os.path.splitext(os.path.basename(self.file_path))[0]
        self.album_name = base_name

        # ID3タグからアルバム名を試行
        try:
            audio_tag = MP3(self.file_path, ID3=ID3)
            if 'TALB' in audio_tag:
                self.album_name = audio_tag['TALB'].text[0]
        except:
            pass

        self.label_file.config(text=os.path.basename(self.file_path), fg="black")
        messagebox.showinfo("読み込み", f"アルバム名を「{self.album_name}」として認識しました。")

    def setup_ffmpeg(self):
        """exe化してもffmpegを見つけられるように設定"""
        if getattr(sys, 'frozen', False):
            base_path = os.path.dirname(sys.executable)
        else:
            base_path = os.path.dirname(os.path.abspath(__file__))
        
        ffmpeg_bin = os.path.join(base_path, "ffmpeg.exe")
        if os.path.exists(ffmpeg_bin):
            AudioSegment.converter = ffmpeg_bin

    def analyze_silence(self):
        if not self.file_path:
            messagebox.showwarning("エラー", "先にファイルを選択してください。")
            return
        
        # 音声読み込み（時間がかかる場合があるためカーソル変更）
        self.root.config(cursor="watch")
        self.root.update()
        
        try:
            self.audio = AudioSegment.from_mp3(self.file_path)
            # 無音検知: -40dB以下が1000ms以上続く場所
            silent_ranges = silence.detect_silence(self.audio, min_silence_len=1000, silence_thresh=-40)
            
            self.text_area.delete("1.0", tk.END)
            for start, end in silent_ranges:
                mid_point = (start + end) / 2
                m, s = int((mid_point / 60000)), int((mid_point / 1000) % 60)
                self.text_area.insert(tk.END, f"{m:02d}:{s:02d} \n")
            
            messagebox.showinfo("解析完了", "無音部分から切れ目を提案しました。\n右側に曲名を貼り付けてください。")
        except Exception as e:
            messagebox.showerror("エラー", f"解析に失敗しました: {e}")
        finally:
            self.root.config(cursor="")

    def split_execute(self):
        if not self.audio: return
        
        lines = self.text_area.get("1.0", tk.END).strip().split('\n')
        if not lines or (len(lines) == 1 and lines[0] == ''):
            messagebox.showwarning("エラー", "分割ポイントが入力されていません。")
            return

        # 出力ディレクトリ作成（アルバム名）
        safe_album_name = "".join([c for c in self.album_name if c.isalnum() or c in (' ', '_', '-')]).strip()
        output_dir = os.path.join(os.path.dirname(self.file_path), safe_album_name)
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

        # タイムスタンプ解析
        points = [(0, "Start")]
        for line in lines:
            if ":" not in line: continue
            parts = line.split(maxsplit=1)
            t_str = parts[0]
            name = parts[1].strip() if len(parts) > 1 else ""
            
            try:
                m, s = map(int, t_str.split(':'))
                ms = (m * 60 + s) * 1000
                points.append((ms, name))
            except:
                continue
        
        points.append((len(self.audio), "End"))
        points.sort()

        # 分割・保存
        self.root.config(cursor="watch")
        self.root.update()
        
        try:
            for i in range(len(points) - 1):
                start_ms, track_name = points[i]
                end_ms = points[i+1][0]
                
                if end_ms - start_ms < 500: continue # 極端に短いセグメントは除外

                filename = f"{i+1:02d}_{track_name}.mp3" if track_name else f"track_{i+1:02d}.mp3"
                chunk = self.audio[start_ms:end_ms]
                chunk.export(os.path.join(output_dir, filename), format="mp3")
            
            messagebox.showinfo("成功", f"フォルダ「{safe_album_name}」に全曲保存しました！")
        except Exception as e:
            messagebox.showerror("エラー", f"保存中にエラーが発生しました: {e}")
        finally:
            self.root.config(cursor="")

if __name__ == "__main__":
    root = tk.Tk()
    app = Mp3SplitterApp(root)
    root.mainloop()