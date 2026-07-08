# 火山引擎Doubao URL API 开启Prompt缓存完整Python示例
## 一、核心说明
火山引擎大模型API缓存分为**请求缓存（prompt缓存）**，通过请求头 `X-Volc-Cache-Enable` 控制开关：
1. 开启缓存：请求头添加 `X-Volc-Cache-Enable: true`
2. 缓存命中标识：响应头返回 `X-Volc-Cache-Hit: true` 代表命中缓存，`false` 为首次生成
3. 缓存键规则：基于完整入参（model、messages、temperature、top_p等全部参数）做哈希，参数变动则缓存失效
4. 缓存有效期：火山引擎默认缓存时效约24小时（平台侧配置，无法客户端自定义）

## 二、完整Python脚本（同步调用，带缓存验证）
```python
import requests
import json

# ====================== 配置区（替换为你的火山引擎凭证）======================
VOLC_ACCESS_KEY = "你的AccessKey"
VOLC_SECRET_KEY = "你的SecretKey"
ENDPOINT_URL = "https://ark.cn-beijing.volces.com/api/v3/chat/completions"  # Doubao通用API地址
ARK_MODEL_ID = "ep-xxxxxxxxx"  # 你的Doubao推理接入点ID
# ============================================================================

def call_doubao_with_cache(prompt: str, enable_cache: bool = True):
    """
    调用Doubao并开启/关闭prompt缓存，返回响应+缓存命中标识
    """
    # 请求头
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {VOLC_ACCESS_KEY}:{VOLC_SECRET_KEY}"
    }
    # 开启缓存关键头
    if enable_cache:
        headers["X-Volc-Cache-Enable"] = "true"

    # 请求体（固定参数，保证缓存可命中）
    payload = {
        "model": ARK_MODEL_ID,
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.0,  # 温度必须固定，随机值会导致缓存失效
        "top_p": 0.7,
        "max_tokens": 1024
    }

    # 发送请求
    resp = requests.post(
        url=ENDPOINT_URL,
        headers=headers,
        json=payload,
        timeout=60
    )
    resp.raise_for_status()

    # 提取缓存命中标识
    cache_hit = resp.headers.get("X-Volc-Cache-Hit", "false")
    cache_key = resp.headers.get("X-Volc-Cache-Key", None)  # 缓存唯一键，可用于排查

    # 解析返回内容
    resp_data = resp.json()
    content = resp_data["choices"][0]["message"]["content"]

    result = {
        "cache_enable": enable_cache,
        "cache_hit": cache_hit,
        "cache_key": cache_key,
        "response_content": content,
        "usage": resp_data["usage"]
    }
    return result


if __name__ == "__main__":
    test_prompt = "用3句话介绍火山引擎Doubao大模型"

    print("===== 第一次调用（无缓存，生成新结果）=====")
    res1 = call_doubao_with_cache(test_prompt, enable_cache=True)
    print(f"是否命中缓存: {res1['cache_hit']}")
    print(f"缓存Key: {res1['cache_key']}")
    print(f"返回内容:\n{res1['response_content']}\n")

    print("===== 第二次调用（相同Prompt，预期命中缓存）=====")
    res2 = call_doubao_with_cache(test_prompt, enable_cache=True)
    print(f"是否命中缓存: {res2['cache_hit']}")
    print(f"缓存Key: {res2['cache_key']}")
    print(f"返回内容:\n{res2['response_content']}\n")

    print("===== 关闭缓存调用（强制不读取缓存）=====")
    res3 = call_doubao_with_cache(test_prompt, enable_cache=False)
    print(f"是否命中缓存: {res3['cache_hit']}")
```

## 三、缓存验证逻辑说明
### 1. 验证标准
- 第一次请求：`X-Volc-Cache-Hit: false`，消耗token计费
- 完全相同参数二次请求：`X-Volc-Cache-Hit: true`，**不消耗输入输出token**（计费0）
- 任意参数修改（temperature、prompt、max_tokens等）：缓存失效，Hit=false

### 2. 关键避坑点（缓存不生效常见原因）
1. temperature不能随机：动态随机温度会让每次请求哈希不同，缓存永远不命中，测试请固定`temperature=0`
2. messages数组完全一致：空格、换行、标点细微变化都会破坏缓存键
3. 不要流式+缓存混用：流式场景缓存支持不稳定，验证缓存建议用同步非流式
4. 接入点ID必须一致：不同ep-id缓存隔离

## 四、流式调用带缓存版本（可选）
```python
def stream_doubao_with_cache(prompt: str):
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {VOLC_ACCESS_KEY}:{VOLC_SECRET_KEY}",
        "X-Volc-Cache-Enable": "true"
    }
    payload = {
        "model": ARK_MODEL_ID,
        "messages": [{"role": "user", "content": prompt}],
        "stream": True,
        "temperature": 0.0
    }
    resp = requests.post(ENDPOINT_URL, headers=headers, json=payload, stream=True)
    print("缓存命中标识:", resp.headers.get("X-Volc-Cache-Hit"))
    for chunk in resp.iter_lines():
        if chunk:
            print(chunk.decode("utf-8"))
```

## 五、排查缓存不生效的方法
1. 打印返回头 `X-Volc-Cache-Key`，两次请求key不一致=参数存在差异
2. 核对全量请求体，确保无动态随机参数
3. 确认开通对应ARK接入点缓存权限（部分存量接入点需工单开通缓存能力）
4. 缓存超过24小时会自动清空，需重新生成缓存