// 注入用户浏览器的取数脚本模板（铺垫占位）。
// 由 AppleScriptBrowserAcquirer 注入到当前页面，必须 JSON.stringify 返回，
// 以便 osascript 把结果以字符串传回 Python 侧再解析。
//
// AI 服务按目标站点补全选择器与抽取逻辑。约定返回 JSON 字符串。

(function () {
  // 示例骨架（无实际逻辑，待补全）：
  // const items = [...document.querySelectorAll('.item')].map(el => ({
  //   title: el.querySelector('h2')?.innerText?.trim(),
  //   url: el.querySelector('a')?.href,
  // }));
  // return JSON.stringify({ ready: document.readyState, items });
  return JSON.stringify({ ready: document.readyState, items: [] });
})();
