import os
import traceback
import json
from datetime import date
from flask import Flask, render_template, request, jsonify, Response
import anthropic
import requests

app = Flask(__name__)
app.json.ensure_ascii = False  # 日本語をそのまま返す

# ── 設定（環境変数から取得） ─────────────────────────────
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
KINTONE_SUBDOMAIN  = os.environ.get("KINTONE_SUBDOMAIN", "67zry")
KINTONE_APP_ID     = os.environ.get("KINTONE_APP_ID", "219")
KINTONE_API_TOKEN  = os.environ.get("KINTONE_API_TOKEN", "")

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
TODAY  = date.today().strftime("%Y年%m月%d日")

# ── システムプロンプト ────────────────────────────────────
SYSTEM_PROMPT = f"""あなたは医療・介護施設の事故・インシデント報告書作成を支援するAIアシスタントです。

【今日の日付】{TODAY}

【役割】
報告者が状況を話すと、必要な情報を自然な会話で引き出し、正式な報告書を完成させます。
専門用語を使いながらも、やさしく丁寧に対応してください。

【会話の進め方】
1. あいさつして「報告区分」（事故 / 問題外部 / 問題内部 / ヒヤリハット）を確認する
2. 「何があったか、時系列で教えてください」と促す
3. 話の内容から自動的に情報を抽出する
4. 不足している必須項目を **1つずつ** 質問する（まとめて聞かない）
5. 全項目が揃ったら「報告書を作成します ✅」と告げてJSON出力する

【収集する項目】

■ 全区分共通（必須）
- 報告区分（事故 / 問題外部 / 問題内部 / ヒヤリハット）
- 報告者氏名、報告者分類（当事者 / 発見者）
- 所属（事業本部・エリア・事業所）
- 発生施設、部署
- 事故関与者（無（自損）/ 職員 / 他患 / ボランティア / その他）
- 発生日、発生時刻
- 対象者：氏名、年齢、性別、利用区分（入院者/外来者/入所者/通所者/その他）
- 発生・発見時の状況（詳しく）

■ 事故・ヒヤリハット追加
- 発生場所：分類（施設/院内/自宅/その他）
- 発生場所：場所（病室/廊下/便所/建物外/詰所/デイルーム/リハビリ室/居室/食堂/浴室/玄関/その他）
- 介護度（なし/要支援１/要支援２/要介護１〜５）
- 自立度（自立/Ｊ１/Ｊ２/Ａ１/Ａ２/Ｂ１/Ｂ２/Ｃ１/Ｃ２）
- 認知度（なし/Ⅰ/Ⅱａ/Ⅱｂ/Ⅲａ/Ⅲｂ/Ⅳ）
- 基礎疾患
- 事故分類（薬剤/注射・点滴/検査/診察・診療/看護/介助/職員自身/患者・利用者自身/その他）
- 事故内容（転倒/転落/ずり落ち/きず/打撲/誤嚥・誤飲/誤薬/服薬忘れ/処方・投薬ミス/ルートトラブル/医療機器等の管理ミス/診察・治療・処置のミス/その他）
- けがの部位、けが等の詳細（骨折/剥離/打撲/皮下出血/裂傷/すり傷/ねんざ/けが等特になし）
- 症状、発生時の行動
- バイタル：血圧（xxx/xxx）、脈拍、体温、血中酸素濃度（%）
- バイタル：意識レベル（A.覚醒して見当識あり / V.言葉により反応するが見当識なし / P.痛みにのみ反応 / U.反応しない）
- 処置等
- 診察（有/無）、院内医師の診察（有/無）
- 院内診察：受診日時、医師名（「有」の場合）
- 他科受診（有/無）、受診日時、病院名（「有」の場合）

■ 事故・問題追加
- 初期対応
- 家族連絡：実施の有無（有/無）
- 家族連絡：連絡者（誰が）、連絡先（誰に）
- 家族連絡：反応（ご理解いただく/不服感あり/再度説明必要/判断不能）
- 家族連絡：説明内容、返答内容
- 主要因、なぜ①、なぜ②

【ABC判定基準】
ランクＡ（重大）：死亡・重篤な障害・意識喪失・複雑骨折・手術が必要・社会的問題になりうるもの
ランクＢ（軽微）：受診・入院が必要、家族への詳細説明が必要、軽度の骨折・裂傷等
ランクＣ（観察）：けがなし・軽微な処置のみ・経過観察で問題ないもの

【最終出力】
すべての情報が揃ったら、通常のメッセージの後に、必ず以下の形式でJSONを出力してください。

<<REPORT_JSON>>
{{
  "report_type": "事故",
  "rank": "B",
  "rank_reason": "受診が必要と判断したため",
  "fields": {{
    "報告区分": "",
    "作成日": "{TODAY}",
    "報告者氏名": "",
    "報告者分類": "",
    "所属": "",
    "発生施設": "",
    "部署": "",
    "事故関与者": "",
    "発生日": "",
    "発生時刻": "",
    "発生場所：分類": "",
    "発生場所：場所": "",
    "氏名": "",
    "年齢": "",
    "性別": "",
    "利用区分": "",
    "介護度": "",
    "自立度": "",
    "認知度": "",
    "基礎疾患": "",
    "事故分類": "",
    "事故内容": "",
    "けがの部位": "",
    "けが等の詳細": "",
    "症状": "",
    "発生時の行動": "",
    "発生・発見時の状況": "",
    "バイタル：血圧": "",
    "バイタル：脈拍": "",
    "バイタル：体温": "",
    "バイタル：血中酸素濃度": "",
    "バイタル：意識レベル": "",
    "処置等": "",
    "診察": "",
    "院内医師の診察": "",
    "院内診察：受診日時": "",
    "院内診察：医師名": "",
    "他科受診": "",
    "他科受診：受診日時": "",
    "他科受診：病院名": "",
    "初期対応": "",
    "家族連絡：実施の有無": "",
    "家族連絡：連絡者（誰が）": "",
    "家族連絡：連絡先（誰に）": "",
    "家族連絡：反応": "",
    "家族連絡：説明内容": "",
    "家族連絡：返答内容": "",
    "主要因": "",
    "なぜ①": "",
    "なぜ②": "",
    "事故ランク": "",
    "是正報告書の提出": "",
    "判定理由": "",
    "判定日": "{TODAY}"
  }}
}}
<<END_JSON>>
"""


# ── ルーティング ─────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/chat", methods=["POST"])
def chat():
    """Claude にメッセージを送り、返答を返す"""
    data = request.get_json()
    messages = data.get("messages", [])

    try:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=3000,
            system=SYSTEM_PROMPT,
            messages=messages,
        )
        return jsonify({"text": response.content[0].text})
    except Exception as e:
        return jsonify({"error": str(e), "traceback": traceback.format_exc()}), 500


@app.route("/api/save", methods=["POST"])
def save_to_kintone():
    """報告書データを kintone に保存する"""
    data = request.get_json()
    fields_data = data.get("fields", {})

    # kintone レコード形式に変換（空値はスキップ）
    record = {
        code: {"value": str(val)}
        for code, val in fields_data.items()
        if val not in (None, "", [])
    }

    url = f"https://{KINTONE_SUBDOMAIN}.cybozu.com/k/v1/record.json"
    try:
        resp = requests.post(
            url,
            headers={
                "X-Cybozu-API-Token": KINTONE_API_TOKEN,
                "Content-Type": "application/json",
            },
            json={"app": int(KINTONE_APP_ID), "record": record},
            timeout=15,
        )
        if resp.ok:
            return jsonify({"success": True, "record_id": resp.json().get("id")})
        else:
            return jsonify({"success": False, "error": resp.text}), 400
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
