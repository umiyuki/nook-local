# nook/common/counters.py
from collections import defaultdict

class CallCounter:
    """LLMとGoogletransの呼び出し回数を追跡するクラス"""
    def __init__(self):
        # 全体のカウント
        self.llm_total = 0
        self.googletrans_total = 0
        # モジュールごとのカウント
        self.llm_by_module = defaultdict(int)
        self.googletrans_by_module = defaultdict(int)
    
    def increment_llm(self, module: str):
        """LLM呼び出しをカウント"""
        self.llm_total += 1
        self.llm_by_module[module] += 1
    
    def increment_googletrans(self, module: str):
        """Googletrans呼び出しをカウント"""
        self.googletrans_total += 1
        self.googletrans_by_module[module] += 1
    
    def report(self):
        """呼び出し回数のレポートを表示"""
        print("\n=== API呼び出し回数レポート ===")
        print(f"総LLM呼び出し回数: {self.llm_total}")
        print(f"総Googletrans呼び出し回数: {self.googletrans_total}")
        print("\nモジュールごとのLLM呼び出し回数:")
        for module, count in self.llm_by_module.items():
            print(f"  {module}: {count}")
        print("\nモジュールごとのGoogletrans呼び出し回数:")
        for module, count in self.googletrans_by_module.items():
            print(f"  {module}: {count}")
        print("====================\n")

# グローバルカウンターインスタンス
counter = CallCounter()