import time
import bs4
import os
import requests
import re
import threading
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

# 设置 Streamlit 界面
st.title("晋江评论爬虫小助手")

# 输入作品 ID 和章节范围
novel_id = st.text_input("请输入作品ID：", "")
chapter_range_input = st.text_input("请输入章节范围（例如：1-5 或 1,3,5）：", "")

# 提取章节范围
def parse_chapter_range(chapter_range_input):
    chapter_range = []
    try:
        if '-' in chapter_range_input:  # 处理连续区间
            start, end = map(int, chapter_range_input.split('-'))
            chapter_range = list(range(start, end + 1))
        elif ',' in chapter_range_input:  # 处理分开的章节号
            chapter_range = list(map(int, chapter_range_input.split(',')))
        else:  # 如果是单个章节
            chapter_range = [int(chapter_range_input)]
    except ValueError:
        st.error("章节范围格式错误，请输入正确的范围（例如：1-5 或 1,3,5）。")
    return chapter_range

# 核心爬取功能
def create_session():
    session = requests.Session()
    retry = Retry(
        total=3,  # 重试次数
        backoff_factor=1,  # 重试延迟时间
        status_forcelist=[500, 502, 503, 504],  # 重试的 HTTP 状态码
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('https://', adapter)
    return session

# 获取章节标题
def get_chapter_titles_v2(novel_id):
    global chapter_titles
    chapter_titles = {}
    try:
        logging.info(f"开始爬取小说 {novel_id} 的章节标题...")
        session = create_session()
        response = session.get(
            f"https://www.jjwxc.net/onebook.php?novelid={novel_id}",
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.110 Safari/537.36",
            },
            timeout=15,
        )

        # 改为使用 "html.parser" 解析器
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

        logging.info(f"成功提取章节标题，共 {len(chapter_titles)} 章。")
    except Exception as e:
        logging.error(f"提取章节标题失败: {e}")

# 获取评论
def get_comments_for_chapter(chapter_id, cookies=""):
    comments_data = []
    try:
        page = 1
        while True:
            logging.info(f"正在获取第 {chapter_id} 章，第 {page} 页评论...")
            response = requests.get(
                "https://www.jjwxc.net/comment.php",
                params={
                    "novelid": novel_id,
                    "chapterid": chapter_id,
                    "page": page,
                },
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.110 Safari/537.36",
                    "Cookie": cookies,
                },
                timeout=15,
            )

            # 改为使用 "html.parser" 解析器
            soup = bs4.BeautifulSoup(response.content.decode("gbk", errors="ignore"), "html.parser")
            comment_divs = soup.find_all("div", id=re.compile(r"comment_\d+"))

            if not comment_divs:
                logging.info(f"第 {chapter_id} 章的第 {page} 页无评论，结束本章爬取。")
                break

            for comment in comment_divs:
                try:
                    comment_text = html2text.html2text(str(comment))
                    time_re = re.compile(r"发表时间：[0-9\-\s:]*")
                    name_re = re.compile(r"网友：\[[\s\S]*?\]")

                    comment_time = time_re.findall(comment_text)[0][5:].strip()
                    try:
                        commenter_name = name_re.findall(comment_text)[0][3:].strip()
                    except IndexError:
                        commenter_name = "匿名用户"

                    chapter_title = chapter_titles.get(chapter_id, "未知章节")

                    chapter_label = f"第{chapter_id}章 {chapter_title}"

                    comments_data.append([comment_time, commenter_name, comment_text, chapter_label, page])

                except Exception as e:
                    logging.error(f"解析评论失败: {e}")

            page += 1
            time.sleep(random.uniform(1, 3))  # 随机延迟

        return comments_data
    except Exception as e:
        logging.error(f"爬取章节 {chapter_id} 评论失败: {e}")
        return []

# 执行爬取
def run_crawler(novel_id, chapter_range):
    get_chapter_titles_v2(novel_id)
    
    all_comments = []
    with ThreadPoolExecutor(max_workers=5) as executor:
        results = executor.map(get_comments_for_chapter, chapter_range)
        for result in results:
            all_comments.extend(result)
            time.sleep(random.uniform(1, 3))  # 防止过于频繁的请求

    return all_comments

# 数据处理与导出
def export_to_excel(comments_data):
    df = pd.DataFrame(comments_data, columns=["评论时间", "评论者", "评论内容", "章节", "页码"])
    output_file = f'novel_{novel_id}_comments_{time.strftime("%Y%m%d_%H%M%S")}.xlsx'
    df.to_excel(output_file, index=False, engine='openpyxl')

    return output_file

# Streamlit 页面交互
if st.button("开始爬取"):
    if not novel_id or not chapter_range_input:
        st.error("请输入作品ID和章节范围")
    else:
        chapter_range = parse_chapter_range(chapter_range_input)
        if chapter_range:
            with st.spinner("正在爬取数据..."):
                all_comments = run_crawler(novel_id, chapter_range)

            if all_comments:
                output_file = export_to_excel(all_comments)
                st.success(f"评论数据已成功保存！文件：{output_file}")
                st.download_button(label="下载评论数据", data=open(output_file, "rb"), file_name=output_file)
        else:
            st.error("章节范围格式错误，请输入正确的范围（例如：1-5 或 1,3,5）。")

# 确保文件存在
def ensure_files_exist():
    if not os.path.exists("messages.txt"):
        with open("messages.txt", "w", encoding="utf-8"):
            pass
    if not os.path.exists("replies.txt"):
        with open("replies.txt", "w", encoding="utf-8"):
            pass

ensure_files_exist()

# 创建一个锁来保证线程安全 
message_lock = threading.Lock()

# 保存留言
def save_message(name, message):
    with message_lock:
        with open("messages.txt", "a", encoding="utf-8") as file:
            file.write(f"{name}: {message}\n")
    st.write(f"已保存留言：{name}: {message}")  # 调试信息

# 保存回复
def save_reply_to_file(reply_index, reply_text):
    with message_lock:
        with open("replies.txt", "a", encoding="utf-8") as file:
            file.write(f"评论 {reply_index}: {reply_text}\n")

# Streamlit 页面交互部分
st.title("💬 留言互动")

# 用户输入留言
name = st.text_input("你的昵称：", "")
message = st.text_area("想对我们说点什么：")

if st.button("提交留言"):
    if message.strip():
        save_message(name, message)
        st.success("谢谢你的留言！我们会认真阅读的 😊")
    else:
        st.error("留言不能为空哦！")

# 显示留言和楼中楼回复
st.write("### 📝 留言板")

try:
    with open("messages.txt", "r", encoding="utf-8") as msg_file:
        messages = msg_file.readlines()

    with open("replies.txt", "r", encoding="utf-8") as reply_file:
        replies = reply_file.readlines()

except FileNotFoundError:
    messages = []
    replies = []

# 分页功能
PAGE_SIZE = 5
if len(messages) > 0:  
    max_page = (len(messages) // PAGE_SIZE) + 1 if len(messages) % PAGE_SIZE != 0 else len(messages) // PAGE_SIZE
    max_page = max(max_page, 1)

    # 如果只有一页，直接显示第一页，不用slider
    if max_page > 1:
        page_num = st.slider("选择你想看的留言页", 1, max_page, 1)
    else:
        page_num = 1  # 如果只有一页，直接设置为1
else:
    page_num = 1  # 如果没有留言，默认显示第一页
    max_page = 1  # 设置最大页数为1
    st.write("目前没有留言哦")

# 当前页的留言
start_idx = (page_num - 1) * PAGE_SIZE
end_idx = start_idx + PAGE_SIZE
paged_messages = messages[start_idx:end_idx]

st.write(f"📄 **显示留言：第 {page_num} 页，共 {max_page} 页**")

# 显示留言和回复
for idx, msg in enumerate(paged_messages):
    user_name, msg_text = msg.split(":", 1)
    related_replies = [r for r in replies if f"评论 {idx + 1}:" in r]
    reply_text = related_replies[0].strip() if related_replies else "暂未回复"

    st.write(f"**{user_name} 的留言：** {msg_text.strip()}")
    st.write(f"**^ ^ 回复：** {reply_text}")

    # 留言回复部分
    reply_index = idx + 1
    reply_text = st.text_area(f"对 {user_name} 的留言回复：", key=f"reply_{reply_index}")
    if st.button(f"提交回复给 {user_name}", key=f"submit_reply_{reply_index}"):

        if reply_text.strip():
            save_reply_to_file(reply_index, reply_text)
            st.success("回复成功！ 😊")
        else:
            st.error("回复不能为空哦！")

# 在 Streamlit 页面显示结尾信息
st.write("---")
st.header("🎉 完成啦！")
st.markdown("""
    久等啦，嘿嘿~ 使用指南和上次的回复已经一起放到这个文档啦~
    请查看：[使用指南与回复](https://docs.qq.com/doc/DT0pkdWR1UkVUZGJx)
""")
