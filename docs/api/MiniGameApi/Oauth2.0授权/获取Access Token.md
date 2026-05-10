Access-Token是调用授权关系接口的调用凭证，用于服务端对API请求鉴权。所有接口均通过请求参数中传递的 Access\_Token来进行身份认证和鉴权。

* Access\_Token有效期为24小时，可使用refresh\_token通过【[刷新Refresh\_Token](https://open.oceanengine.com/labels/7/docs/1696710506097679)】获取新的AccessToken

关键信息

详情

是否支持SDK

支持

# 请求地址

<https://api.oceanengine.com/open_api/oauth2/access_token/>
[可视化调试](https://open.oceanengine.com/tools/visual_debug.html?docId=1696710505596940)
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
| app\_id  必填 | number | 开发者应用ID  可在开发者后台-应用管理处查看 |
| appid | number | 兼容老字段，待下线 |
| secret  必填 | string | 开发者应用的私钥Secret  应用管理页面选择应用编辑即可进入查看到应用详情信息  **注意：**填入secret与app\_id需对应，否则将会报错 |
| auth\_code  必填 | string | 授权码，在授权完成后回调时会提供该授权码，授权介绍可参考：【[应用如何申请账户授权](https://open.oceanengine.com/labels/41/docs/1812506430648330)】  **注意：**10分钟有效期，且只能使用一次 |

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
PATH = "/open_api/oauth2/access_token/"
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
    auth_code = AUTH_CODE
​
    # Args in JSON format
    my_args = "{\"app_id\": \"%s\", \"appid\": \"%s\", \"secret\": \"%s\", \"auth_code\": \"%s\"}" % (app_id, appid, secret, auth_code)
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
    private static final String PATH = "/open_api/oauth2/access_token/";
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
        String auth_code = AUTH_CODE;
​
        // Args in JSON format
        String myArgs = String.format("{\"app_id\": \"%s\", \"appid\": \"%s\", \"secret\": \"%s\", \"auth_code\": \"%s\"}",app_id, appid, secret, auth_code);
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
$PATH = "/open_api/oauth2/access_token/";
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
$auth_code = AUTH_CODE;
​
/* Args in JSON format */
$my_args = sprintf("{\"app_id\": \"%s\", \"appid\": \"%s\", \"secret\": \"%s\", \"auth_code\": \"%s\"}", $app_id, $appid, $secret, $auth_code);
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
    "auth_code": "AUTH_CODE"
}' \
https://api.oceanengine.com/open_api/oauth2/access_token/
```

# 应答字段

| 字段 | 类型 | 描述 |
| --- | --- | --- |
| code | number | 返回码,详见 [【附录-返回码】](https://open.oceanengine.com/labels/7/docs/1696710760866831) |
| message | string | 返回信息,详见 [【附录-返回码】](https://open.oceanengine.com/labels/7/docs/1696710760866831) |
| data | json | json返回值 |
| access\_token | string | 请求接口时Header中传入的Access\_Token，用于验证权限的token |
| refresh\_token | string | 刷新Token，用于获取新的access\_token和refresh\_token，并且刷新过期时间 |
| expires\_in | number | Access\_Token剩余有效时间，单位（秒） |
| refresh\_token\_expires\_in | number | refresh\_token剩余有效时间，单位（秒） |
| advertiser\_ids | number[] |  |
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

