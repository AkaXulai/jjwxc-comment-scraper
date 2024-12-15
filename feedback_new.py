import time
import bs4
import requests
import re
import logging
import html2text
import pandas as pd
import random
from concurrent.futures import ThreadPoolExecutor
import streamlit as st
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry

# 配置日志格式
logging.basicConfig(format='%(asctime)s - %(message)s', level=logging.INFO)

# Streamlit 页面设置
st.title("晋江评论小助手")
st.write("👋 欢迎使用，这里可以帮你快速爬取晋江文学城的章节评论并导出成 Excel 文件！")

# 输入小说 ID 和章节范围
novel_id = st.text_input("📘 请输入作品 ID：", "")
chapter_range_input = st.text_input("📖 请输入章节范围（例如：1-5 或 1,3,5）：", "")

# 提取章节范围
def parse_chapter_range(chapter_range_input):
    chapter_range = []
    try:
        if '-' in chapter_range_input:  # 连续区间
            start, end = map(int, chapter_range_input.split('-'))
            chapter_range = list(range(start, end + 1))
        elif ',' in chapter_range_input:  # 指定章节
            chapter_range = list(map(int, chapter_range_input.split(',')))
        else:  # 单一章节
            chapter_range = [int(chapter_range_input)]
    except ValueError:
        st.error("章节范围格式错误，请输入正确的范围（例如：1-5 或 1,3,5）。")
    return chapter_range

# 创建会话
def create_session():
    session = requests.Session()
    retry = Retry(total=3, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('https://', adapter)
    return session

# 获取章节标题
def get_chapter_titles_v2(novel_id):
    global chapter_titles
    chapter_titles = {}
    try:
        logging.info(f"正在获取小说 {novel_id} 的章节标题...")
        session = create_session()
        response = session.get(
            f"https://www.jjwxc.net/onebook.php?novelid={novel_id}",
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=15,
        )

        soup = bs4.BeautifulSoup(response.content.decode("gbk", errors="ignore"), "html.parser")
        rows = soup.select("tr")
        for row in rows:
            cells = row.find_all("td")
            if len(cells) < 2:
                continue

            chapter_id = cells[0].get_text(strip=True)
            chapter_title = cells[1].get_text(strip=True)

            if chapter_id.isdigit():
                chapter_titles[int(chapter_id)] = chapter_title

        logging.info(f"获取到 {len(chapter_titles)} 个章节标题。")
    except Exception as e:
        logging.error(f"获取章节标题失败: {e}")

# 获取评论
def get_comments_for_chapter(chapter_id, cookies=""):
    comments_data = []
    try:
        page = 1
        while True:
            logging.info(f"正在获取第 {chapter_id} 章，第 {page} 页的评论...")
            response = requests.get(
                "https://www.jjwxc.net/comment.php",
                params={"novelid": novel_id, "chapterid": chapter_id, "page": page},
                headers={"User-Agent": "Mozilla/5.0", "Cookie": cookies},
                timeout=15,
            )

            soup = bs4.BeautifulSoup(response.content.decode("gbk", errors="ignore"), "html.parser")
            comment_divs = soup.find_all("div", id=re.compile(r"comment_\\d+"))

            if not comment_divs:
                logging.info(f"第 {chapter_id} 章，第 {page} 页没有更多评论。")
                break

            for comment in comment_divs:
                try:
                    comment_text = html2text.html2text(str(comment))
                    time_re = re.compile(r"发表时间：[0-9\-\s:]*")
                    name_re = re.compile(r"网友：\[[\s\S]*?\]")

                    comment_time = time_re.findall(comment_text)[0][5:].strip()
                    commenter_name = name_re.findall(comment_text)[0][3:].strip() if name_re.findall(comment_text) else "匿名用户"

                    chapter_title = chapter_titles.get(chapter_id, "未知章节")
                    chapter_label = f"第{chapter_id}章 {chapter_title}"

                    comments_data.append([comment_time, commenter_name, comment_text, chapter_label, page])
                except Exception as e:
                    logging.error(f"解析评论失败: {e}")

            page += 1
            time.sleep(random.uniform(1, 3))

        return comments_data
    except Exception as e:
        logging.error(f"爬取第 {chapter_id} 章评论失败: {e}")
        return []

# 执行爬取
def run_crawler(novel_id, chapter_range):
    get_chapter_titles_v2(novel_id)
    all_comments = []
    with ThreadPoolExecutor(max_workers=5) as executor:
        results = executor.map(get_comments_for_chapter, chapter_range)
        for result in results:
            all_comments.extend(result)
            time.sleep(random.uniform(1, 3))

    return all_comments

# 导出评论数据到 Excel
def export_to_excel(comments_data):
    df = pd.DataFrame(comments_data, columns=["评论时间", "评论者", "评论内容", "章节", "页码"])
    output_file = f'novel_{novel_id}_comments_{time.strftime("%Y%m%d_%H%M%S")}.xlsx'
    df.to_excel(output_file, index=False, engine='openpyxl')
    return output_file

# Streamlit 界面交互
if st.button("开始爬取"):
    if not novel_id or not chapter_range_input:
        st.error("❗ 请填写作品 ID 和章节范围。")
    else:
        chapter_range = parse_chapter_range(chapter_range_input)
        if chapter_range:
            with st.spinner("⏳ 正在努力爬取数据中，请稍候..."):
                all_comments = run_crawler(novel_id, chapter_range)

            if all_comments:
                output_file = export_to_excel(all_comments)
                st.success("✅ 评论爬取完成！")
                st.download_button(
                    label="📂 点击下载评论数据", 
                    data=open(output_file, "rb"), 
                    file_name=output_file
                )
            else:
                st.warning("⚠️ 未能获取到任何评论数据，请检查输入信息。")
        else:
            st.error("❌ 章节范围格式错误，请重新输入。")

# 添加留言互动区
st.write("---")
st.header("💬 留言互动")

# 保存留言及回复
def save_message(name, message):
    with open("messages.txt", "a", encoding="utf-8") as file:
        file.write(f"{name}: {message}\n")

def save_reply(index, reply):
    with open("replies.txt", "a", encoding="utf-8") as file:
        file.write(f"{index}: {reply}\n")

# 用户输入留言
name = st.text_input("你的名字：", "匿名用户")
message = st.text_area("想对我们说点什么：")

if st.button("提交留言"):
    if message.strip():
        save_message(name, message)
        st.success("谢谢你的留言！我们会认真阅读的 😊")
    else:
        st.error("留言不能为空哦！")

# 显示留言及管理员回复
st.write("### 📝 留言板")
try:
    with open("messages.txt", "r", encoding="utf-8") as msg_file:
        messages = msg_file.readlines()

    with open("replies.txt", "r", encoding="utf-8") as reply_file:
        replies = reply_file.readlines()
except FileNotFoundError:
    messages = []
    replies = []

if messages:
    for idx, msg in enumerate(messages):
        st.write(f"{idx + 1}. {msg.strip()}")
        corresponding_reply = next((r.split(": ", 1)[1].strip() for r in replies if r.startswith(f
