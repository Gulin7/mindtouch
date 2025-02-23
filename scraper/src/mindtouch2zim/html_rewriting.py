import re

from zimscraperlib.rewriting.html import (
    AttrsList,
    format_attr,
    get_attr_value_from,
)
from zimscraperlib.rewriting.html import rules as html_rules
from zimscraperlib.rewriting.url_rewriting import (
    ArticleUrlRewriter,
    HttpUrl,
    RewriteResult,
    ZimPath,
)

from mindtouch2zim.client import LibraryPage
from mindtouch2zim.constants import logger
from mindtouch2zim.utils import is_better_srcset_descriptor
from mindtouch2zim.vimeo import get_vimeo_thumbnail_url

# remove all standard rules, they are not adapted to Vue.JS UI
html_rules.rewrite_attribute_rules.clear()
html_rules.rewrite_data_rules.clear()
html_rules.rewrite_tag_rules.clear()

rewriting_context = None


@html_rules.rewrite_attribute()
def rewrite_href_src_srcset_attributes(
    tag: str,
    attr_name: str,
    attr_value: str | None,
    url_rewriter: ArticleUrlRewriter,
    base_href: str | None,
):
    """Rewrite href and src attributes"""
    if attr_name not in ("href", "src", "srcset") or not attr_value:
        return
    if not isinstance(url_rewriter, HtmlUrlsRewriter):
        raise Exception("Expecting HtmlUrlsRewriter")
    new_attr_value = None
    if tag in ["a", "area"]:
        rewrite_result = url_rewriter(
            attr_value, base_href=base_href, rewrite_all_url=False
        )
        # rewrite links for proper navigation inside ZIM Vue.JS UI (if inside ZIM) or
        # full link (if outside the current library)
        new_attr_value = (
            f"#/{rewrite_result.rewriten_url[len(url_rewriter.library_path.value) :]}"
            if rewrite_result.rewriten_url.startswith(url_rewriter.library_path.value)
            else rewrite_result.rewriten_url
        )
    else:
        # we remove the src/href/srcset which is not supported, to ensure we won't load
        # external assets
        new_attr_value = ""
        logger.warning(
            f"Unsupported '{attr_name}' encountered in '{tag}' tag (value: "
            f"'{attr_value}') while rewriting {rewriting_context}"
        )
    return (attr_name, new_attr_value)


YOUTUBE_IFRAME_RE = re.compile(r".*youtube(?:-\w+)*\.\w+\/embed\/(?P<id>.*?)(?:\?.*)*$")
VIMEO_IFRAME_RE = re.compile(r".*vimeo(?:-\w+)*\.\w+\/video\/(?:.*?)(?:\?.*)*$")


@html_rules.rewrite_tag()
def rewrite_iframe_tags(
    tag: str,
    attrs: AttrsList,
    base_href: str | None,
    url_rewriter: ArticleUrlRewriter,
):
    """Rewrite youtube and vimeo iframes to remove player until video is included"""
    if tag not in ["iframe"]:
        return
    if not isinstance(url_rewriter, HtmlUrlsRewriter):
        raise Exception("Expecting HtmlUrlsRewriter")
    src = get_attr_value_from(attrs=attrs, name="src")
    if not src:
        logger.warning(f"Empty src found in iframe while rewriting {rewriting_context}")
        return
    image_rewriten_url = None
    try:
        if ytb_match := YOUTUBE_IFRAME_RE.match(src):
            rewrite_result = url_rewriter(
                f'https://i.ytimg.com/vi/{ytb_match.group("id")}/hqdefault.jpg',
                base_href=base_href,
            )
            url_rewriter.add_item_to_download(rewrite_result)
            image_rewriten_url = rewrite_result.rewriten_url
        elif VIMEO_IFRAME_RE.match(src):
            rewrite_result = url_rewriter(
                get_vimeo_thumbnail_url(src),
                base_href=base_href,
            )
            url_rewriter.add_item_to_download(rewrite_result)
            image_rewriten_url = rewrite_result.rewriten_url
        else:
            logger.debug(
                f"iframe pointing to {src} in {rewriting_context} will not "
                "have any preview"
            )
    except Exception as exc:
        logger.warning(
            f"Failed to rewrite iframe with src {src} in  {rewriting_context}",
            exc_info=exc,
        )

    if image_rewriten_url:
        return (
            f'<a href="{src}" target="_blank">'
            f'<div class="zim-removed-video">'
            f'<img src="content/{image_rewriten_url}">'
            "</img>"
            "</div>"
            "</a>"
            '<iframe style="display: none;">'  # fake opening tag just to remove iframe
        )
    else:
        # replace iframe with text indicating the online URL which has not been ZIMed
        return (
            f"This content is not inside the ZIM. "
            f'View content online at <a href="{src}" target="_blank">'
            f"<div>"
            f"{src}"
            "</div>"
            "</a>"
            '<iframe style="display: none;">'  # fake opening tag just to remove iframe
        )


class HtmlUrlsRewriter(ArticleUrlRewriter):
    """A rewriter for HTML processing

    This rewriter does not store items to download on-the-fly but has containers and
    metadata so that HTML rewriting rules can decide what needs to be downloaded
    """

    def __init__(
        self, library_url: str, page: LibraryPage, existing_zim_paths: set[ZimPath]
    ):
        super().__init__(
            article_url=HttpUrl(f"{library_url}/{page.path}"),
            article_path=ZimPath("index.html"),
            existing_zim_paths=existing_zim_paths,
        )
        self.library_url = library_url
        self.library_path = ArticleUrlRewriter.normalize(HttpUrl(f"{library_url}/"))
        self.items_to_download: dict[ZimPath, set[HttpUrl]] = {}

    def __call__(
        self, item_url: str, base_href: str | None, *, rewrite_all_url: bool = True
    ) -> RewriteResult:
        result = super().__call__(item_url, base_href, rewrite_all_url=rewrite_all_url)
        return result

    def add_item_to_download(self, rewrite_result: RewriteResult):
        """Add item to download based on rewrite result"""
        if rewrite_result.zim_path is not None:
            # if item is expected to be inside the ZIM, store asset information so that
            # we can download it afterwards
            if rewrite_result.zim_path in self.items_to_download:
                self.items_to_download[rewrite_result.zim_path].add(
                    HttpUrl(rewrite_result.absolute_url)
                )
            else:
                self.items_to_download[rewrite_result.zim_path] = {
                    HttpUrl(rewrite_result.absolute_url)
                }


@html_rules.rewrite_tag()
def rewrite_img_tags(
    tag: str,
    attrs: AttrsList,
    base_href: str | None,
    url_rewriter: ArticleUrlRewriter,
    *,
    auto_close: bool,
):

    if tag != "img":
        return
    if not isinstance(url_rewriter, HtmlUrlsRewriter):
        raise Exception("Expecting HtmlUrlsRewriter")
    if not (srcset_value := get_attr_value_from(attrs, "srcset")):
        # simple case, just need to rewrite the src
        src_value = get_attr_value_from(attrs, "src")
        if src_value is None:
            return  # no need to rewrite this img without src
    else:
        scrset_values = [value.strip() for value in srcset_value.split(",")]
        best_src_value = None
        best_descriptor = None
        for src_value in scrset_values:
            # Ignore RUF005 which prefer to avoid concatenation, because I didn't found
            # another way to wwite this which still please pyright type checker, which
            # is not capable to properly infer types of results with other syntaxes
            url, descriptor = (src_value.rsplit(" ", 1) + [None])[:2]  # noqa: RUF005
            if best_src_value is None:
                best_src_value = url
                best_descriptor = descriptor
                continue
            if is_better_srcset_descriptor(
                new_descriptor=descriptor, current_best_descriptor=best_descriptor
            ):
                best_src_value = url
                best_descriptor = descriptor

        src_value = best_src_value

    rewrite_result = url_rewriter(src_value, base_href=base_href, rewrite_all_url=True)
    # add 'content/' to the URL since all assets will be stored in the sub.-path
    new_attr_value = f"content/{rewrite_result.rewriten_url}"
    url_rewriter.add_item_to_download(rewrite_result)

    values = " ".join(
        format_attr(*attr)
        for attr in [
            (attr_name, attr_value)
            for (attr_name, attr_value) in attrs
            if attr_name not in ["src", "srcset", "sizes"]
        ]
        + [("src", new_attr_value)]
    )
    return f"<img {values}{'/>' if auto_close else '>'}"
