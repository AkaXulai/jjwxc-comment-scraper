import time
import bs4
import requests
import re
import logging
import html2text
import pandas as pd
import threading
import streamlit as st
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry

# 配置日志格式
logging.basicConfig(format='%(asctime)s - %(message)s', level=logging.INFO)

# 设置 Streamlit 界面
st.title("晋江文学城评论爬虫")

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
    """
    爬取小说主页的章节标题，适配嵌套不规则的 HTML 结构。
    """
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

        # 解析 HTML 内容
        soup = bs4.BeautifulSoup(response.content.decode("gbk", errors="ignore"), "lxml")

        # 尝试从章节列表中提取
        rows = soup.select("tr")  # 假定章节数据以表格呈现
        for row in rows:
            cells = row.find_all("td")
            if len(cells) < 2:
                continue  # 跳过无效行

            chapter_id = cells[0].get_text(strip=True)
            chapter_title = cells[1].get_text(strip=True)

            # 过滤有效章节号
            if chapter_id.isdigit():
                chapter_titles[int(chapter_id)] = chapter_title

        logging.info(f"成功提取章节标题，共 {len(chapter_titles)} 章。")
    except Exception as e:
        logging.error(f"提取章节标题失败: {e}")

# 获取评论
def get_comments_for_chapter(chapter_id, cookies=""):
    """
    爬取指定章节的所有评论
    """
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

            # 解析评论
            soup = bs4.BeautifulSoup(response.content.decode("gbk", errors="ignore"), "lxml")
            comment_divs = soup.find_all("div", id=re.compile(r"comment_\d+"))

            # 如果没有更多评论，结束爬取
            if not comment_divs:
                logging.info(f"第 {chapter_id} 章的第 {page} 页无评论，结束本章爬取。")
                break

            for comment in comment_divs:
                try:
                    # 提取评论内容
                    comment_text = html2text.html2text(str(comment))
                    time_re = re.compile(r"发表时间：[0-9\-\s:]*")
                    name_re = re.compile(r"网友：\[[\s\S]*?\]")

                    # 提取评论时间和用户
                    comment_time = time_re.findall(comment_text)[0][5:].strip()
                    try:
                        commenter_name = name_re.findall(comment_text)[0][3:].strip()
                    except IndexError:
                        commenter_name = "匿名用户"

                    # 获取章节标题
                    chapter_title = chapter_titles.get(chapter_id, "未知章节")

                    # 合并章节号和标题
                    chapter_label = f"第{chapter_id}章 {chapter_title}"

                    # 保存评论到数据列表
                    comments_data.append([comment_time, commenter_name, comment_text, chapter_label, page])

                except Exception as e:
                    logging.error(f"解析评论失败: {e}")

            # 下一页
            page += 1
            time.sleep(3)

        return comments_data
    except Exception as e:
        logging.error(f"爬取章节 {chapter_id} 评论失败: {e}")
        return []

# 执行爬取
def run_crawler(novel_id, chapter_range):
    # 获取章节标题
    get_chapter_titles_v2(novel_id)
    
    all_comments = []
    for chapter_id in chapter_range:
        comments = get_comments_for_chapter(chapter_id)
        all_comments.extend(comments)
        time.sleep(3)  # 防止频繁请求

    return all_comments

# 数据处理与导出
def export_to_excel(comments_data):
    # 将评论数据转化为 pandas DataFrame
    df = pd.DataFrame(comments_data, columns=["评论时间", "评论者", "评论内容", "章节", "页码"])

    # 修改文件名并保存到 Excel 文件
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
            # 启动爬虫
            with st.spinner("正在爬取数据..."):
                all_comments = run_crawler(novel_id, chapter_range)

            if all_comments:
                # 导出到 Excel 文件
                output_file = export_to_excel(all_comments)
                st.success(f"评论数据已成功保存！文件：{output_file}")
                st.download_button(label="下载评论数据", data=open(output_file, "rb"), file_name=output_file)
        else:
            st.error("章节范围格式错误，请输入正确的范围（例如：1-5 或 1,3,5）。")
