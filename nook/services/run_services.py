"""
Nookの各サービスを実行するスクリプト。
情報を収集し、ローカルストレージに保存します。
"""

import os
import argparse
from datetime import datetime
from dotenv import load_dotenv
from nook.common.counters import counter

# 環境変数の読み込み
load_dotenv()

# GitHubトレンドサービス
from nook.services.github_trending.github_trending import GithubTrending

# 他のサービスをインポート（クラス名を修正）
from nook.services.hacker_news.hacker_news import HackerNewsRetriever
from nook.services.reddit_explorer.reddit_explorer import RedditExplorer
from nook.services.tech_feed.tech_feed import TechFeed
from nook.services.paper_summarizer.paper_summarizer import PaperSummarizer
from nook.services.twitter_poster.twitter_poster import TwitterPoster

def run_github_trending():
    """
    GitHubトレンドサービスを実行します。
    """
    print("GitHubトレンドリポジトリを収集しています...")
    github_trending = GithubTrending()
    github_trending.run()
    print("GitHubトレンドリポジトリの収集が完了しました。")

def run_hacker_news():
    """
    Hacker Newsサービスを実行します。
    """
    print("Hacker News記事を収集しています...")
    try:
        # クラス名を修正
        hacker_news = HackerNewsRetriever()
        hacker_news.run(20)
        print("Hacker News記事の収集が完了しました。")
    except Exception as e:
        print(f"Hacker News記事の収集中にエラーが発生しました: {str(e)}")

def run_reddit_explorer():
    """
    Redditエクスプローラーサービスを実行します。
    """
    print("Reddit投稿を収集しています...")
    try:
        # APIキーの確認
        if not os.environ.get("REDDIT_CLIENT_ID") or not os.environ.get("REDDIT_CLIENT_SECRET"):
            print("警告: REDDIT_CLIENT_ID または REDDIT_CLIENT_SECRET が設定されていません。")
            print("Reddit APIを使用するには、これらの環境変数を設定してください。")
            return
            
        reddit_explorer = RedditExplorer()
        reddit_explorer.run(5)
        print("Reddit投稿の収集が完了しました。")
    except Exception as e:
        print(f"Reddit投稿の収集中にエラーが発生しました: {str(e)}")

def run_tech_feed():
    """
    技術フィードサービスを実行します。
    """
    print("技術ブログのフィードを収集しています...")
    try:
        tech_feed = TechFeed()
        tech_feed.run()
        print("技術ブログのフィードの収集が完了しました。")
    except Exception as e:
        print(f"技術ブログのフィード収集中にエラーが発生しました: {str(e)}")

def run_paper_summarizer():
    """
    論文要約サービスを実行します。
    """
    print("arXiv論文を収集・要約しています...")
    try:
        # Grok APIキーの確認
        if not os.environ.get("GROK_API_KEY"):
            print("警告: GROK_API_KEY が設定されていません。")
            print("論文要約には Grok API が必要です。")
            return
            
        paper_summarizer = PaperSummarizer()
        paper_summarizer.run()
        print("論文の収集・要約が完了しました。")
    except Exception as e:
        print(f"論文の収集・要約中にエラーが発生しました: {str(e)}")

def run_twitter_poster():
    """
    Twitterポスターサービスを実行します。
    """
    print("収集した情報をXにポストしています...")
    try:
        # Twitter APIキーの確認
        required_keys = ["CONSUMER_KEY", "CONSUMER_SECRET", "BEARER_TOKEN", "ACCESS_TOKEN", "ACCESS_SECRET"]
        missing_keys = [key for key in required_keys if not os.environ.get(key)]
        
        if missing_keys:
            print(f"警告: 以下のTwitter API環境変数が設定されていません: {', '.join(missing_keys)}")
            print("Twitter APIを使用するには、これらの環境変数を設定してください。")
            return
            
        twitter_poster = TwitterPoster()
        twitter_poster.run()
        print("Xへの投稿が完了しました。")
    except Exception as e:
        print(f"Xへの投稿中にエラーが発生しました: {str(e)}")

def run_twitter_github():
    """
    GitHub Trendingの情報をXにポストします。
    """
    print("GitHub Trendingの情報をXにポストしています...")
    try:
        # Twitter APIキーの確認
        required_keys = ["CONSUMER_KEY", "CONSUMER_SECRET", "BEARER_TOKEN", "ACCESS_TOKEN", "ACCESS_SECRET"]
        missing_keys = [key for key in required_keys if not os.environ.get(key)]
        
        if missing_keys:
            print(f"警告: 以下のTwitter API環境変数が設定されていません: {', '.join(missing_keys)}")
            print("Twitter APIを使用するには、これらの環境変数を設定してください。")
            return
            
        twitter_poster = TwitterPoster()
        twitter_poster.post_github_trending()
        print("GitHub Trendingの情報のポストが完了しました。")
    except Exception as e:
        print(f"Xへの投稿中にエラーが発生しました: {str(e)}")

def run_twitter_hackernews():
    """
    Hacker Newsの情報をXにポストします。
    """
    print("Hacker Newsの情報をXにポストしています...")
    try:
        # Twitter APIキーの確認
        required_keys = ["CONSUMER_KEY", "CONSUMER_SECRET", "BEARER_TOKEN", "ACCESS_TOKEN", "ACCESS_SECRET"]
        missing_keys = [key for key in required_keys if not os.environ.get(key)]
        
        if missing_keys:
            print(f"警告: 以下のTwitter API環境変数が設定されていません: {', '.join(missing_keys)}")
            print("Twitter APIを使用するには、これらの環境変数を設定してください。")
            return
            
        twitter_poster = TwitterPoster()
        twitter_poster.post_hacker_news()
        print("Hacker Newsの情報のポストが完了しました。")
    except Exception as e:
        print(f"Xへの投稿中にエラーが発生しました: {str(e)}")

def run_twitter_arxiv():
    """
    arXiv論文の情報をXにポストします。
    """
    print("arXiv論文の情報をXにポストしています...")
    try:
        # Twitter APIキーの確認
        required_keys = ["CONSUMER_KEY", "CONSUMER_SECRET", "BEARER_TOKEN", "ACCESS_TOKEN", "ACCESS_SECRET"]
        missing_keys = [key for key in required_keys if not os.environ.get(key)]
        
        if missing_keys:
            print(f"警告: 以下のTwitter API環境変数が設定されていません: {', '.join(missing_keys)}")
            print("Twitter APIを使用するには、これらの環境変数を設定してください。")
            return
            
        twitter_poster = TwitterPoster()
        twitter_poster.post_arxiv_papers()
        print("arXiv論文の情報のポストが完了しました。")
    except Exception as e:
        print(f"Xへの投稿中にエラーが発生しました: {str(e)}")

def run_twitter_reddit():
    """
    Reddit記事の情報をXにポストします。
    """
    print("Reddit記事の情報をXにポストしています...")
    try:
        # Twitter APIキーの確認
        required_keys = ["CONSUMER_KEY", "CONSUMER_SECRET", "BEARER_TOKEN", "ACCESS_TOKEN", "ACCESS_SECRET"]
        missing_keys = [key for key in required_keys if not os.environ.get(key)]
        
        if missing_keys:
            print(f"警告: 以下のTwitter API環境変数が設定されていません: {', '.join(missing_keys)}")
            print("Twitter APIを使用するには、これらの環境変数を設定してください。")
            return
            
        twitter_poster = TwitterPoster()
        twitter_poster.post_reddit_articles()
        print("Reddit記事の情報のポストが完了しました。")
    except Exception as e:
        print(f"Xへの投稿中にエラーが発生しました: {str(e)}")

def run_twitter_techfeed():
    """
    技術ブログ記事の情報をXにポストします。
    """
    print("技術ブログ記事の情報をXにポストしています...")
    try:
        # Twitter APIキーの確認
        required_keys = ["CONSUMER_KEY", "CONSUMER_SECRET", "BEARER_TOKEN", "ACCESS_TOKEN", "ACCESS_SECRET"]
        missing_keys = [key for key in required_keys if not os.environ.get(key)]
        
        if missing_keys:
            print(f"警告: 以下のTwitter API環境変数が設定されていません: {', '.join(missing_keys)}")
            print("Twitter APIを使用するには、これらの環境変数を設定してください。")
            return
            
        twitter_poster = TwitterPoster()
        twitter_poster.post_tech_feed()
        print("技術ブログ記事の情報のポストが完了しました。")
    except Exception as e:
        print(f"Xへの投稿中にエラーが発生しました: {str(e)}")

def main():
    """
    コマンドライン引数に基づいて、指定されたサービスを実行します。
    """
    parser = argparse.ArgumentParser(description="Nookサービスを実行します")
    parser.add_argument(
        "--service", 
        type=str,
        choices=["all", "github", "hackernews", "reddit", "techfeed", "paper", "twitter", 
                "twitter_github", "twitter_hackernews", "twitter_arxiv", "twitter_reddit", "twitter_techfeed"],
        default="all",
        help="実行するサービス (デフォルト: all)"
    )
    
    args = parser.parse_args()
    
    if args.service == "all" or args.service == "github":
        run_github_trending()
    
    if args.service == "all" or args.service == "hackernews":
        run_hacker_news()
    
    if args.service == "all" or args.service == "reddit":
        run_reddit_explorer()
    
    if args.service == "all" or args.service == "techfeed":
        run_tech_feed()
    
    if args.service == "all" or args.service == "paper":
        run_paper_summarizer()
    
    if args.service == "twitter":
        run_twitter_poster()
    
    # 個別のTwitter投稿オプション
    if args.service == "twitter_github":
        run_twitter_github()
    
    if args.service == "twitter_hackernews":
        run_twitter_hackernews()
    
    if args.service == "twitter_arxiv":
        run_twitter_arxiv()
    
    if args.service == "twitter_reddit":
        run_twitter_reddit()
    
    if args.service == "twitter_techfeed":
        run_twitter_techfeed()

    # 実行完了後にレポートを表示
    counter.report()

if __name__ == "__main__":
    main() 