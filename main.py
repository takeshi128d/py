import tkinter as tk
from tkinter import filedialog, messagebox
import pandas as pd
import os
from itertools import combinations

# デフォルトのディレクトリパスをMacのDownloadsフォルダに最適化しております。
DEFAULT_DIR = "/Users/takeshi.nakane/Downloads"


class PurchaseAnalysisApp:
    def __init__(self, root):
        self.root = root
        self.root.title("購買分析ツール - リスト分割・重複排除・検証")
        self.root.geometry("700x550")

        self.label = tk.Label(root, text="複数の会員IDリスト(CSV)を選択し、処理を開始してください。")
        self.label.pack(pady=10)

        self.product_label = tk.Label(root, text="出力フォルダに付ける商材名を入力してください（任意）:")
        self.product_label.pack(pady=5)

        self.product_entry = tk.Entry(root, width=40)
        self.product_entry.pack(pady=5)

        self.upload_btn = tk.Button(root, text="ファイルを選択して処理開始", command=self.process_files, bg="lightblue")
        self.upload_btn.pack(pady=10)

        self.log_text = tk.Text(root, height=20, width=85)
        self.log_text.pack(pady=10)

    def log(self, message):
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.root.update()

    def extract_retail_name(self, filename):
        name_without_ext = os.path.splitext(filename)[0]
        parts = name_without_ext.split('_')

        if len(parts) == 1:
            return parts[0]

        first_part = parts[0]
        last_part = parts[-1]

        if first_part[0] in ['①', '②', '③', '④', '⑤', '1', '2', '3']:
            return last_part
        else:
            return first_part

    def get_priority_mark(self, filename):
        """
        ファイル名から明示的な優先順位（①②③など）を判定いたします。
        記号がない場合は 99 を返し、その後の件数による並べ替えに委ねます。
        """
        priority_marks = ['①', '②', '③', '④', '⑤', '⑥', '⑦', '⑧', '⑨', '⑩']
        for i, mark in enumerate(priority_marks):
            if mark in filename:
                return i
        return 99

    def safe_read_csv(self, file_path):
        encodings = ['utf-8-sig', 'utf-8', 'shift_jis', 'cp932']
        for enc in encodings:
            try:
                return pd.read_csv(file_path, encoding=enc, engine="python", dtype=str)
            except UnicodeDecodeError:
                continue
        raise ValueError(f"{os.path.basename(file_path)} の文字コード判定に失敗いたしました。")

    def process_files(self):
        initial_dir = DEFAULT_DIR if os.path.exists(DEFAULT_DIR) else os.path.expanduser("~")

        file_paths = filedialog.askopenfilenames(
            initialdir=initial_dir,
            title="処理するファイル群を選択してください（複数選択可）",
            filetypes=[("CSVファイル", "*.csv")]
        )

        if not file_paths:
            return

        self.log_text.delete(1.0, tk.END)
        self.log("処理を開始いたします...\n")

        retail_groups = {}
        for path in file_paths:
            basename = os.path.basename(path)
            retail_name = self.extract_retail_name(basename)

            if retail_name not in retail_groups:
                retail_groups[retail_name] = []
            retail_groups[retail_name].append(path)

        product_name = self.product_entry.get().strip()
        folder_name = f"出力結果_{product_name}" if product_name else "出力結果"
        output_dir = os.path.join(os.path.dirname(file_paths[0]), folder_name)

        os.makedirs(output_dir, exist_ok=True)
        self.log(f"出力先フォルダ: {output_dir}\n")

        summary_reports = []
        overlap_details = []

        for retail_name, paths in retail_groups.items():
            self.log(f"【リテール名: {retail_name}】の処理を開始します (対象ファイル数: {len(paths)})")

            data_frames = {}
            for path in paths:
                try:
                    df = self.safe_read_csv(path)
                    data_frames[path] = df
                except Exception as e:
                    self.log(f"  [エラー] {os.path.basename(path)}: {e}")
                    continue

            # ---------------------------------------------------------
            # 【重要】優先順位の決定ロジック
            # 1. まずファイル名の記号（①、②など）で並べ替えます。
            # 2. 記号がない（全て同じ優先度）場合は、元データの件数が少ない順に優先します。
            # ---------------------------------------------------------
            sorted_paths = sorted(
                data_frames.keys(),
                key=lambda p: (self.get_priority_mark(os.path.basename(p)), len(data_frames[p]))
            )

            # --- 検証フェーズ（ABC分析） ---
            original_sets = {}
            for path in sorted_paths:
                df = data_frames[path]
                if not df.empty:
                    id_col = df.columns[0]
                    original_sets[os.path.basename(path)] = set(df[id_col].dropna().tolist())

            file_names = list(original_sets.keys())
            for r in range(2, len(file_names) + 1):
                for combo in combinations(file_names, r):
                    intersect = set.intersection(*[original_sets[f] for f in combo])
                    if len(intersect) > 0:
                        kept = combo[0]  # sorted_paths順なので、一番優先度が高いファイルが残存先
                        removed = list(combo[1:])
                        overlap_details.append({
                            'リテール名': retail_name,
                            '重複発生パターン': " ∩ ".join(combo),
                            '重複ID件数': len(intersect),
                            '最終的な残存先': kept,
                            '除外されたファイル': "、".join(removed)
                        })

            # --- 処理フェーズ ---
            seen_ids = set()

            for path in sorted_paths:
                df = data_frames[path]
                original_name = os.path.basename(path)

                if df.empty:
                    self.log(f"  - {original_name}: データが0件のためスキップいたします。")
                    continue

                id_column = df.columns[0]
                df = df.dropna(subset=[id_column])
                initial_count = len(df)

                df_dedup = df[~df[id_column].isin(seen_ids)].copy()
                dedup_count = len(df_dedup)
                duplicates_removed = initial_count - dedup_count

                seen_ids.update(df_dedup[id_column])

                self.log(f"  - {original_name}: 元件数 {initial_count}件 -> "
                         f"重複除外 {duplicates_removed}件 -> 有効件数 {dedup_count}件")

                if dedup_count == 0:
                    self.log("    有効データがないため、分割出力をスキップいたします。")
                    summary_reports.append({
                        'リテール名': retail_name,
                        'ファイル名': original_name,
                        '元の件数': initial_count,
                        '重複による除外件数': duplicates_removed,
                        '最終有効件数': dedup_count,
                        '90%ファイル件数': 0,
                        '10%ファイル件数': 0
                    })
                    continue

                df_shuffled = df_dedup.sample(frac=1, random_state=42).reset_index(drop=True)
                split_index = int(dedup_count * 0.9)

                df_90 = df_shuffled.iloc[:split_index]
                df_10 = df_shuffled.iloc[split_index:]

                name_without_ext = os.path.splitext(original_name)[0]
                file_90_path = os.path.join(output_dir, f"{name_without_ext}_90percent.csv")
                file_10_path = os.path.join(output_dir, f"{name_without_ext}_10percent.csv")

                try:
                    df_90.to_csv(file_90_path, index=False, encoding="utf-8-sig")
                    df_10.to_csv(file_10_path, index=False, encoding="utf-8-sig")
                    self.log(f"    -> 分割出力完了: 90%({len(df_90)}件), 10%({len(df_10)}件)")

                    summary_reports.append({
                        'リテール名': retail_name,
                        'ファイル名': original_name,
                        '元の件数': initial_count,
                        '重複による除外件数': duplicates_removed,
                        '最終有効件数': dedup_count,
                        '90%ファイル件数': len(df_90),
                        '10%ファイル件数': len(df_10)
                    })
                except Exception as e:
                    self.log(f"    [エラー] ファイル保存中にエラーが発生いたしました: {e}")

            self.log("-" * 50)

        if summary_reports:
            pd.DataFrame(summary_reports).to_csv(
                os.path.join(output_dir, "00_件数推移サマリーレポート.csv"),
                index=False, encoding="utf-8-sig"
            )
        if overlap_details:
            pd.DataFrame(overlap_details).to_csv(
                os.path.join(output_dir, "00_重複詳細レポート(セグメント間分析).csv"),
                index=False, encoding="utf-8-sig"
            )

        self.log("すべての処理が完了いたしました。出力先フォルダおよびレポートをご確認くださいませ。")
        messagebox.showinfo("完了", "ファイルの処理、分割、および検証レポートの出力が完了いたしました。")


if __name__ == "__main__":
    root = tk.Tk()
    app = PurchaseAnalysisApp(root)
    root.mainloop()
