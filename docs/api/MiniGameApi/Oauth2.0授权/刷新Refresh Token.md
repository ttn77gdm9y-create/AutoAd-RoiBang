Refresh\_Token在有效期内，可以通过接口刷新Access\_Token，刷新会同时获得新的AccessToken及RefreshToken并更新效期时间（不会影响已有授权关系），同时原Token也会失效，再次刷新需要使用本次刷新获取的新的RefreshToken。

Refresh\_Token、Access\_Token、auth\_code失效后，只能通过重新申请授权获取，建议在调用Token相关接口时避免并发请求。

关键信息

详情

是否支持SDK

支持

# 请求地址

<https://api.oceanengine.com/open_api/oauth2/refresh_token/>
[可视化调试](https://open.oceanengine.com/tools/visual_debug.html?docId=1696710506097679)
[SDK下载](https://open.oceanengine.com/labels/7/docs/1773083358100557)
[MCP调用](https://open.oceanengine.com/labels/7/docs/1847394521222599)

# 请求方法

POST

# Header

| 字段 | 类型 | 描述 |
| --- | --- | --- |
| Content-Type  必填 | string | 请求消息类型 允许值: `application/json` |

# 请求参数

| 字段 | 类型 | 描述 |
| --- | --- | --- |
| app\_id  必填 | number | 开发者申请的应用APP\_ID，可通过【[应用管理](https://open.oceanengine.com/developer/admin/ad_list)】界面查看 |
| appid | number |  |
| secret  必填 | string | 开发者应用的私钥Secret，可通过【[应用管理](https://open.oceanengine.com/developer/admin/ad_list)】界面编辑应用查看   * 传入app\_id与secret需对应，及同一应用下信息 |
| refresh\_token  必填 | string | 刷新token，从「[获取Access Token](https://open.oceanengine.com/labels/7/docs/1696710505596940)」和「[刷新Access Token](https://ad.oceanengine.com/openapi/doc/index.html?id=1696710506097679)」的返回结果中得到，刷新后会过期，请及时保存最新的token |

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
PATH = "/open_api/oauth2/refresh_token/"
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
def post(json_str):
    # type: (str) -> dict
    """
    Send POST request
    :param json_str: Args in JSON format
    :return: Response in JSON format
    """
    url = build_url(PATH)
    args = json.loads(json_str)
    headers = {
        "Access-Token": ACCESS_TOKEN,
        "Content-Type": "application/json",
    }
    rsp = requests.post(url, headers=headers, json=args)
    return rsp.json()
    
​
if __name__ == '__main__':
    app_id = APP_ID
    appid = APPID
    secret = SECRET
    refresh_token = REFRESH_TOKEN
​
    # Args in JSON format
    my_args = "{\"app_id\": \"%s\", \"appid\": \"%s\", \"secret\": \"%s\", \"refresh_token\": \"%s\"}" % (app_id, appid, secret, refresh_token)
    print(post(my_args))
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
    private static final String PATH = "/open_api/oauth2/refresh_token/";
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
     * Send POST request
     *
     * @param jsonStr Args in JSON format
     * @return Response in JSON format
     */
    private static String post(String jsonStr) throws IOException, URISyntaxException {
        OkHttpClient client = new OkHttpClient().newBuilder().build();
        String url = buildUrl(PATH);
​
        RequestBody body = RequestBody.create(MediaType.parse("application/json"), jsonStr);
        Request request = new Request.Builder()
                .url(url)
                .method("POST", body)
                .addHeader("Content-Type", "application/json")
                .addHeader("Access-Token", ACCESS_TOKEN)
                .build();
        Response response = client.newCall(request).execute();
        return response.body().string();
    }
    
​
    public static void main(String[] args) throws IOException, URISyntaxException {
        Long app_id = APP_ID;
        Long appid = APPID;
        String secret = SECRET;
        String refresh_token = REFRESH_TOKEN;
​
        // Args in JSON format
        String myArgs = String.format("{\"app_id\": \"%s\", \"appid\": \"%s\", \"secret\": \"%s\", \"refresh_token\": \"%s\"}",app_id, appid, secret, refresh_token);
        System.out.println(post(myArgs));
    }
}
​
```

---

**Php**

```php
​
$ACCESS_TOKEN = "xxx";
$PATH = "/open_api/oauth2/refresh_token/";
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
​
/**
 * Send POST request
 * @param $json_str : Args in JSON format
 * @return bool|string : Response in JSON format
 */
function post($json_str)
{
    global $ACCESS_TOKEN, $PATH;
    $curl = curl_init();
​
    $url = build_url($PATH);
​
    curl_setopt_array($curl, array(
        CURLOPT_URL => $url,
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_ENCODING => "",
        CURLOPT_MAXREDIRS => 10,
        CURLOPT_TIMEOUT => 0,
        CURLOPT_FOLLOWLOCATION => true,
        CURLOPT_HTTP_VERSION => CURL_HTTP_VERSION_1_1,
        CURLOPT_CUSTOMREQUEST => "POST",
        CURLOPT_POSTFIELDS => $json_str,
        CURLOPT_HTTPHEADER => array(
            "Content-Type: application/json",
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
$app_id = APP_ID;
$appid = APPID;
$secret = SECRET;
$refresh_token = REFRESH_TOKEN;
​
/* Args in JSON format */
$my_args = sprintf("{\"app_id\": \"%s\", \"appid\": \"%s\", \"secret\": \"%s\", \"refresh_token\": \"%s\"}", $app_id, $appid, $secret, $refresh_token);
echo post($my_args);
​
```

---

**Curl**

```bash
curl -H "Access-Token:xxx" -H "Content-Type:application/json" -X POST \
-d '{
    "app_id": "APP_ID",
    "appid": "APPID",
    "secret": "SECRET",
    "refresh_token": "REFRESH_TOKEN"
}' \
https://api.oceanengine.com/open_api/oauth2/refresh_token/
```

# 应答字段

| 字段 | 类型 | 描述 |
| --- | --- | --- |
| code | number | 返回码,详见 [【附录-返回码】](https://open.oceanengine.com/labels/7/docs/1696710760866831) |
| message | string | 返回信息,详见 [【附录-返回码】](https://open.oceanengine.com/labels/7/docs/1696710760866831) |
| data | json | json返回值 |
| access\_token | string | 用于接口访问验证权限的Access\_Token |
| refresh\_token | string | Refresh\_Token，刷新Token，用于获取新的access\_token和refresh\_token |
| expires\_in | number | Access\_Token剩余有效时间，单位（秒） |
| refresh\_token\_expires\_in | number | Refresh\_Token剩余有效时间，单位（秒） |
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

