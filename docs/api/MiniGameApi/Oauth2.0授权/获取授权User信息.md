可根据AccessToken查询Token对应授权账号信息，对应token拥有权限点、接口范围、敏感物料授权信息。

* 新增权限点需要重新申请客户授权并获取新的AccessToken
* 当开发者账户主体信息与操作业务账户主体信息不一致时，涉及获取敏感物料信息的接口需要敏感物料授权权限才可以获取，例如：获取线索列表，获取评论，获取视频/图片素材返回的预览链接等。

关键信息

详情

是否支持SDK

支持

# 请求地址

<https://api.oceanengine.com/open_api/2/user/info/>
[可视化调试](https://open.oceanengine.com/tools/visual_debug.html?docId=1696710507039756)
[SDK下载](https://open.oceanengine.com/labels/7/docs/1773083358100557)
[MCP调用](https://open.oceanengine.com/labels/7/docs/1847394521222599)

# 请求方法

GET

# Header

| 字段 | 类型 | 描述 |
| --- | --- | --- |
| Access-Token  必填 | string | 授权access\_token，可以通过【[获取Access token](https://open.oceanengine.com/labels/7/docs/1696710505596940)】接口获取 |

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
PATH = "/open_api/2/user/info/"
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
​
    # Args in JSON format
    my_args = "{}" % ()
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
    private static final String PATH = "/open_api/2/user/info/";
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
​
        // Args in JSON format
        String myArgs = String.format("{}",);
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
$PATH = "/open_api/2/user/info/";
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
​
/* Args in JSON format */
$my_args = sprintf("{}", );
echo get($my_args);
​
```

---

**Curl**

```bash
curl --get -H "Access-Token:xxx" \
​
https://api.oceanengine.com/open_api/2/user/info/
```

# 应答字段

| 字段 | 类型 | 描述 |
| --- | --- | --- |
| code | number | 返回码,详见 [【附录-返回码】](https://open.oceanengine.com/labels/7/docs/1696710760866831) |
| message | string | 返回信息,详见 [【附录-返回码】](https://open.oceanengine.com/labels/7/docs/1696710760866831) |
| data | json | json返回值 |
| display\_name | string | 用户名 |
| email | string | 邮箱（脱敏结果） |
| id | number | 用户id |
| material\_auth\_status | bool | 是否敏感物料授权 |
| app\_id | number | AccessToken对应关联开发者应用APPID |
| token\_scope\_list | number[] | 授权的应用权限点列表 |
| token\_api\_list | string[] | 当前token可操作的api接口列表 |
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

