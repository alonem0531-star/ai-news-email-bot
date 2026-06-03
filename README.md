# AI News LINE Bot

MacやGitHub ActionsでAI関連ニュースをRSSから取得し、重要そうな5件をLINEまたはメールに通知するPythonプロジェクトです。

## ファイル構成

```text
ai-news-line-bot/
├─ main.py
├─ .github/workflows/daily-ai-news-email.yml
├─ .env
├─ requirements.txt
├─ news_cache.json
├─ com.local.ai-news-line-bot.plist
├─ launchd.out.log
└─ launchd.err.log
```

`launchd.out.log` と `launchd.err.log` は、自動実行後に作られるログファイルです。

## 事前準備

1. LINE DevelopersでMessaging APIチャネルを作成します。
2. チャネルアクセストークンを発行します。
3. 作成したLINE公式アカウントを、自分のLINEで友だち追加します。
4. 自分の `userId` を確認します。

LINE Messaging APIのPush messageは、公式ドキュメント上 `POST https://api.line.me/v2/bot/message/push` に `Authorization: Bearer {channel access token}` を付けて送信します。

`userId` はWebhookで取得するのが正式な方法です。いったん試すだけなら、LINE DevelopersのWebhookイベントを受け取れる一時URLを用意し、自分が公式アカウントにメッセージを送った時のイベントJSONから `source.userId` を確認してください。

## セットアップ

ターミナルで以下を実行します。

```bash
cd /Users/minmin/ai-news-line-bot
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

`.env` を開いて、以下を自分の値に変更します。

```env
LINE_CHANNEL_ACCESS_TOKEN=your_line_channel_access_token_here
LINE_USER_ID=your_line_user_id_here
```

必要ならRSSも変更できます。

```env
RSS_FEEDS=https://example.com/feed.xml,https://example.com/rss
```

未設定の場合は、Google News、VentureBeat AI、MIT Technology Review AIのRSSを使います。

メール送信で使う場合は以下を設定します。

```env
DELIVERY_CHANNEL=email
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your_gmail_address@gmail.com
SMTP_PASSWORD=your_gmail_app_password
EMAIL_FROM=your_gmail_address@gmail.com
EMAIL_TO=alonem0531@gmail.com
```

## 手動実行

```bash
cd /Users/minmin/ai-news-line-bot
source .venv/bin/activate
python main.py
```

成功するとLINEにニュースが届き、送信済みURLが `news_cache.json` に保存されます。同じURLは次回以降通知されません。

## launchdで毎朝8時に自動実行

仮想環境を使う場合は、`com.local.ai-news-line-bot.plist` の以下の行を変更してください。

```xml
<string>cd /Users/minmin/ai-news-line-bot &amp;&amp; /usr/bin/python3 main.py</string>
```

変更後:

```xml
<string>cd /Users/minmin/ai-news-line-bot &amp;&amp; /Users/minmin/ai-news-line-bot/.venv/bin/python main.py</string>
```

plistをLaunchAgentsにコピーして読み込みます。

```bash
cp /Users/minmin/ai-news-line-bot/com.local.ai-news-line-bot.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.local.ai-news-line-bot.plist
launchctl enable gui/$(id -u)/com.local.ai-news-line-bot
```

すぐに動作確認したい場合:

```bash
launchctl kickstart -k gui/$(id -u)/com.local.ai-news-line-bot
```

停止したい場合:

```bash
launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.local.ai-news-line-bot.plist
```

## ログ確認

```bash
cat /Users/minmin/ai-news-line-bot/launchd.out.log
cat /Users/minmin/ai-news-line-bot/launchd.err.log
```

エラーが出る場合は、`.env` のトークンと `LINE_USER_ID`、LINE公式アカウントを友だち追加済みかを確認してください。

## ニュースの絞り込み

`main.py` 内の `IMPORTANT_KEYWORDS` に重みを設定しています。OpenAI、ChatGPT、Claude、Gemini、生成AIなどを高めにして、スコアの高いニュースを5件選びます。

## GitHub Actionsで毎朝メール送信

`.github/workflows/daily-ai-news-email.yml` は毎日 `04:05 Asia/Tokyo` に実行されます。GitHubのスケジュールはUTC基準なので、workflowでは `19:05 UTC` を指定しています。

GitHub repositoryの `Settings > Secrets and variables > Actions > Repository secrets` に以下を登録してください。

```text
SMTP_USERNAME
SMTP_PASSWORD
EMAIL_FROM
```

Gmailを使う場合、`SMTP_PASSWORD` には通常のGoogleアカウントパスワードではなく、Googleアカウントの2段階認証を有効にしたうえで発行するアプリパスワードを入れてください。

手動テストはGitHubのActions画面から `Daily AI News Email` を選び、`Run workflow` で実行できます。
