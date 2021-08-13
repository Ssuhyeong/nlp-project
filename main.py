import os

from flask import Flask
from flask_sqlalchemy import SQLAlchemy

from summarize import summarize
from util.email_sender import send_email
from util.news import crawl_news

app = Flask(__name__)

app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', "sqlite:///:memory:")
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)


class News(db.Model):
    __tablename__ = 'news'

    id = db.Column('id', db.Integer, primary_key=True, autoincrement=True)
    title = db.Column(db.Text, nullable=False)
    link = db.Column(db.Text, nullable=False, unique=True)
    description = db.Column(db.Text, nullable=False)
    contents = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    updated_at = db.Column(db.DateTime, default=db.func.current_timestamp(),
                           onupdate=db.func.current_timestamp())

    def __init__(self, title, link, description, contents):
        self.title = title
        self.link = link
        self.contents = contents
        self.description = description


@app.route('/', methods=['POST'])
def crawl_news_save():
    query = request.form['query']

    news = crawl_news(query, start=1, offset=2)

    news_records = []

    for n in news:
        news_records.append(News(
            title=n['title'],
            contents=n['contents'],
            link=n['link'],
            description=n['description']
        ))

    db.session.add_all(news_records)
    db.session.commit()

    return 'ok'


@app.route('/subscribe', methods=['GET'])
def subscribe():
    q = request.args.get('query')

    news = crawl_news(q, start=1, offset=2)

    top5_latest_news = news[:5]

    for n in top5_latest_news:
        contents = n['contents']
        summarized_contents = summarize(contents)

        send_email(
            subject=n['title'],
            from_email='kyeongwook.ma@gmail.com',
            to_email='kyeongwook.ma@gmail.com',
            basic_text=summarized_contents
        )

    return 'ok'


@app.route('/test', methods=['GET'])
def test():
    return 'test'


LINE_CHANNEL_SECRET = '2fc19e1093b60c91e0b1a631decc5df4'
LINE_CLIENT_TOKEN = 'FHgZHvx8uOBZ0O9ik4b6OUCvziaRIilIDJxczOwAOigoqcP0mulxT4AwgNjvzYUhCBCZyfAT2CYG7AO3eLleJusihEk9TE1W2evS5viiDiKVntHvI5uJVJWIDh9SuxDKCocvO9Bzi/hBIPAlspxsGwdB04t89/1O/w1cDnyilFU='

from flask import request, abort

from linebot import (
    LineBotApi, WebhookHandler
)
from linebot.exceptions import (
    InvalidSignatureError
)
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage, ConfirmTemplate, MessageAction, TemplateSendMessage,
)

line_bot_api = LineBotApi(LINE_CLIENT_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)


@app.route('/callback', methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']

    body = request.get_data(as_text=True)
    print(body)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)

    return 'ok'


COMMAND = '구독'


AVAILABE_STATUS = ['INIT',  # 0
                   'SUBSCRIBING',  # 1
                   'INPUT_EMAIL',  # 2
                   'CONFIRM_EMAIL',  # 3
                   'QUERY'  # 4
                   ]

user_status = AVAILABE_STATUS[0]
user_email = ''

from kss import split_sentences

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    global user_status
    global user_email

    input_text = event.message.text
    phrases = split_sentences(input_text, use_heuristic=True)

    # 이메일 입력
    if user_status == AVAILABE_STATUS[0] and COMMAND in phrases:
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text='입력받을 이메일 주소를 입력해주세요.')
        )
        user_status = AVAILABE_STATUS[2]

    # 이메일 확인
    elif user_status == AVAILABE_STATUS[2]:
        email = event.message.text
        user_email = email

        confirm_template = ConfirmTemplate(text='이 이메일이 맞나요?',
                                       actions=[
                                           MessageAction(label='Yes', text='네'),
                                           MessageAction(label='No', text='아니오'),
                                       ]
                                       )

        template_message = TemplateSendMessage(
            alt_text='이메일 주소 입력',
            template=confirm_template
        )

        line_bot_api.reply_message(event.reply_token, template_message)

        user_status = AVAILABE_STATUS[3]

    elif user_status == AVAILABE_STATUS[3]:
        choice = event.message.text

        # 응답에 따른 상태 변화
        if choice == '네':
            user_status = AVAILABE_STATUS[4]
        elif choice == '아니오':
            user_status = AVAILABE_STATUS[0]

    elif user_status == AVAILABE_STATUS[4]:

        # 검색어로 네이버 뉴스 크롤링
        query = event.message.text

        news = crawl_news(query, start=1, offset=2)

        # 5개만 추림
        top5_latest_news = news[:5]

        for n in top5_latest_news:
            contents = n['contents']
            summarized_contents = summarize(contents)

            if len(summarized_contents) == '':
                continue

            # 이메일 발송
            send_email(
                subject=n['title'],
                from_email='tngud124@naver.com',
                to_email = user_email,
                basic_text=summarized_contents
            )

        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text='{} 의 검색어로 {} 의 요약본을 전송했습니다.'
                            .format(query, user_email)
                            )
        )
    # 처리 못할 시
    else:
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text='무슨 말씀이신지 잘 모르겠습니다.')
        )

if __name__ == '__main__':
    db.create_all()
    port = os.getenv('PORT', 8000)
    app.run(debug=True, port=port)