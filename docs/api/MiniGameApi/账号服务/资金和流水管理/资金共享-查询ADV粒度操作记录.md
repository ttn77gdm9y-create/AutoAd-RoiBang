查询ADV粒度的共享钱包操作记录

关键信息

详情

是否支持SDK

支持

权限点及应用类型

了解如何 [申请授权&生成授权](https://open.oceanengine.com/labels/7/docs/1803016515293203?origin=metadata)

权限点:  账号服务-资金和流水管理-共享钱包

应用类型:  自研投放应用-客户/代理商/独立三方站点/群峰上架服务、提供第三方服务-客户/代理商/独立三方站点/群峰上架服务

接入能力范围:  巨量 PC

支持的账户类型

客户投放账户

代理商账户

巨量引擎工作台账户

本地推

升级版巨量引擎工作台账户

# 请求地址

https://api.oceanengine.com/open\_api/v3.0/shared\_wallet/wallet\_adv\_operation\_log/get/[可视化调试](https://open.oceanengine.com/tools/visual_debug.html?docId=1848384541742468)
[SDK下载](https://open.oceanengine.com/labels/7/docs/1773083358100557)

# 请求方法

GET

# Header

| 字段 | 类型 | 描述 |
| --- | --- | --- |
| Access-Token  必填 | string | 授权access\_token，可以通过【[获取Access token](https://open.oceanengine.com/labels/7/docs/1696710505596940)】接口获取 |

# 请求参数

| 字段 | 类型 | 描述 |
| --- | --- | --- |
| account\_id  必填 | number |  |
| account\_type  必填 | string | 账号类型，代理商/直客 可选值:    * `AGENT` 代理 * `BP` BP |
| wallet\_id  必填 | number | 操作的目标 |
| filtering  必填 | object | 过滤条件 |
| adv\_id | number | adv\_id & operation\_id 两个必填一个 |
| operation\_id | number | adv\_id & operation\_id 两个必填一个 |
| status\_filter | string | 可选, 状态过滤 可选值:    * `all` 所有状态 * `only_finish` 只取终态 |
| page  必填 | number | 页码 |
| page\_size  必填 | number | 每页数量 |

# 请求示例

**Python**

```python
# coding=utf-8
import json
import requests
​
from six import string_types
from six.moves.urllib.parse import urlencode, urlunparse  # noqa
​
ACCESS_TOKEN = "xxx"
PATH = "/open_api/v3.0/shared_wallet/wallet_adv_operation_log/get/"
​
​
def build_url(path, query=""):
    # type: (str, str) -> str
    """
    Build request URL
    :param path: Request path
    :param query: Querystring
    :return: Request URL
    """
    scheme, netloc = "https", "api.oceanengine.com"
    return urlunparse((scheme, netloc, path, "", query, ""))
​
def get(json_str):
    # type: (str) -> dict
    """
    Send GET request
    :param json_str: Args in JSON format
    :return: Response in JSON format
    """
    args = json.loads(json_str)
    query_string = urlencode({k: v if isinstance(v, string_types) else json.dumps(v) for k, v in args.items()})
    url = build_url(PATH, query_string)
    headers = {
        "Access-Token": ACCESS_TOKEN,
    }
    rsp = requests.get(url, headers=headers)
    return rsp.json()
    
​
if __name__ == '__main__':
    account_id = ACCOUNT_ID
    account_type = ACCOUNT_TYPE
    wallet_id = WALLET_ID
    adv_id = ADV_ID
    operation_id = OPERATION_ID
    status_filter = STATUS_FILTER
    page = PAGE
    page_size = PAGE_SIZE
​
    # Args in JSON format
    my_args = "{\"account_id\": \"%s\", \"account_type\": \"%s\", \"wallet_id\": \"%s\", \"filtering\": {\"adv_id\": \"%s\", \"operation_id\": \"%s\", \"status_filter\": \"%s\"}, \"page\": \"%s\", \"page_size\": \"%s\"}" % (account_id, account_type, wallet_id, adv_id, operation_id, status_filter, page, page_size)
    print(get(my_args))
```

---

**Java**

```java
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import okhttp3.*;
import org.apache.http.client.utils.URIBuilder;
​
import java.io.IOException;
import java.net.URI;
import java.net.URISyntaxException;
import java.net.URL;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;
​
public class Demo {
    private static final String ACCESS_TOKEN = "xxx";
    private static final String PATH = "/open_api/v3.0/shared_wallet/wallet_adv_operation_log/get/";
    private static final ObjectMapper mapper = new ObjectMapper();
​
    /**
     * Build request URL
     *
     * @param path Request path
     * @return Request URL
     */
    private static String buildUrl(String path) throws URISyntaxException {
        URI uri = new URI("https", "api.oceanengine.com", path, "", "");
        return uri.toString();
    }
​
    
    /**
     * Send GET request
     *
     * @param jsonStr:Args in JSON format
     * @return Response in JSON format
     */
    private static String get(String jsonStr) throws IOException, URISyntaxException {
        OkHttpClient client = new OkHttpClient().newBuilder().build();
        URIBuilder ub = new URIBuilder(buildUrl(PATH));
        Map< String, Object > map = mapper.readValue(jsonStr, Map.class);
        map.forEach((k, v) -> {
            try {
                ub.addParameter(k, v instanceof String ? (String) v : mapper.writeValueAsString(v));
            } catch (JsonProcessingException e) {
                e.printStackTrace();
            }
        });
        URL url = ub.build().toURL();
​
        Request request = new Request.Builder()
                .url(url)
                .method("GET", null)
                .addHeader("Access-Token", ACCESS_TOKEN)
                .build();
        Response response = client.newCall(request).execute();
        return response.body().string();
    }
    
​
    public static void main(String[] args) throws IOException, URISyntaxException {
        Long account_id = ACCOUNT_ID;
        String account_type = ACCOUNT_TYPE;
        Long wallet_id = WALLET_ID;
        Long adv_id = ADV_ID;
        Long operation_id = OPERATION_ID;
        String status_filter = STATUS_FILTER;
        Long page = PAGE;
        Long page_size = PAGE_SIZE;
​
        // Args in JSON format
        String myArgs = String.format("{\"account_id\": \"%s\", \"account_type\": \"%s\", \"wallet_id\": \"%s\", \"filtering\": {\"adv_id\": \"%s\", \"operation_id\": \"%s\", \"status_filter\": \"%s\"}, \"page\": \"%s\", \"page_size\": \"%s\"}",account_id, account_type, wallet_id, adv_id, operation_id, status_filter, page, page_size);
        System.out.println(get(myArgs));
    }
}
​
```

---

**Php**

```php
​
$ACCESS_TOKEN = "xxx";
$PATH = "/open_api/v3.0/shared_wallet/wallet_adv_operation_log/get/";
​
/**
 * Build request URL
 * @param $path : Request path
 * @return string
 */
function build_url($path)
{
    return "https://api.oceanengine.com" . $path;
}
​
/**
 * Send GET request
 * @param $json_str : Args in JSON format
 * @return bool|string : Response in JSON format
 */
function get($json_str)
{
    global $ACCESS_TOKEN, $PATH;
    $curl = curl_init();
​
    $args = json_decode($json_str, true);
​
    /* Values of querystring is also in JSON format */
    foreach ($args as $key => $value) {
        $args[$key] = is_string($value) ? $value : json_encode($value);
    }
​
    $url = build_url($PATH) . "?" . http_build_query(
            $args
        );
​
    curl_setopt_array($curl, array(
        CURLOPT_URL => $url,
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_ENCODING => "",
        CURLOPT_MAXREDIRS => 10,
        CURLOPT_TIMEOUT => 0,
        CURLOPT_FOLLOWLOCATION => true,
        CURLOPT_HTTP_VERSION => CURL_HTTP_VERSION_1_1,
        CURLOPT_CUSTOMREQUEST => "GET",
        CURLOPT_HTTPHEADER => array(
            "Access-Token: " . $ACCESS_TOKEN,
        ),
    ));
​
    $response = curl_exec($curl);
    curl_close($curl);
    return $response;
}
​
​
$account_id = ACCOUNT_ID;
$account_type = ACCOUNT_TYPE;
$wallet_id = WALLET_ID;
$adv_id = ADV_ID;
$operation_id = OPERATION_ID;
$status_filter = STATUS_FILTER;
$page = PAGE;
$page_size = PAGE_SIZE;
​
/* Args in JSON format */
$my_args = sprintf("{\"account_id\": \"%s\", \"account_type\": \"%s\", \"wallet_id\": \"%s\", \"filtering\": {\"adv_id\": \"%s\", \"operation_id\": \"%s\", \"status_filter\": \"%s\"}, \"page\": \"%s\", \"page_size\": \"%s\"}", $account_id, $account_type, $wallet_id, $adv_id, $operation_id, $status_filter, $page, $page_size);
echo get($my_args);
​
```

---

**Curl**

```bash
curl --get -H "Access-Token:xxx" \
--data-urlencode "account_id=ACCOUNT_ID" \
--data-urlencode "account_type=ACCOUNT_TYPE" \
--data-urlencode "wallet_id=WALLET_ID" \
--data-urlencode "filtering={\"adv_id\": \"ADV_ID\", \"operation_id\": \"OPERATION_ID\", \"status_filter\": \"STATUS_FILTER\"}" \
--data-urlencode "page=PAGE" \
--data-urlencode "page_size=PAGE_SIZE" \
https://api.oceanengine.com/open_api/v3.0/shared_wallet/wallet_adv_operation_log/get/
```

# 应答字段

| 字段 | 类型 | 描述 |
| --- | --- | --- |
| code | number | 返回码,详见 [【附录-返回码】](https://open.oceanengine.com/labels/7/docs/1696710760866831) |
| message | string | [返回信息,详见](https://open.oceanengine.com/labels/7/docs/1696710760866831) [【附录-返回码】](https://open.oceanengine.com/labels/7/docs/1696710760866831) |
| data | json | json返回值 |
| wallet\_id | number | 操作的目标 |
| list | object[] | 分页查询列表 |
| wallet\_id | number | 操作的目标 |
| operation\_id | number | 操作id |
| wallet\_operation\_type | string | 操作类型 可选值:    * `bind` 关系绑定 * `unbind` 关系解绑 |
| status | string | 状态 可选值:    * `fail` 终止态, 失败 * `prepare` 初始态, 准备 * `success` 终止态, 成功 * `triggered` 过程态, 异步任务已触发 * `unbind_suspend` 过程态, 解绑的停投操作已完成 |
| adv\_id | number | adv\_id |
| adv\_name | string | adv\_name |
| operation\_detail | object | 详情信息, 根据 wallet\_operation\_type 的不同而变化 |
| relation\_change\_operation\_detail | object | 关系变更详情 |
| fail\_code | number | 失败原因 |
| fail\_reason | string | 失败原因 |
| has\_suspend | bool | 账号是否停投 |
| page\_info | object | 分页信息 |
| page | number | 页码 |
| page\_size | number | 页面大小 |
| total\_page | number | 总页数 |
| total\_number | number | 总数 |
| request\_id | string | 请求日志id |

# 应答示例

```
HTTPS/1.1 200 OK
{
    "message": "OK",
    "code": 0,
    "data": {}
}
```

