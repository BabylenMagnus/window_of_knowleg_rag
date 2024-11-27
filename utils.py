import html2text

import requests


def url2text(url: str):
    # TODO обработка ошибок, с url

    h = html2text.HTML2Text()
    h.ignore_images = True  # Ignore images
    h.ignore_links = True  # Ignore external links
    response = requests.get(url)
    markdown_text = h.handle(response.text)
    return markdown_text
