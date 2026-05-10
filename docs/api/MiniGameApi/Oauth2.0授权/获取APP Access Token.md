> 应用级token获取

关键信息

详情

是否支持SDK

支持

# 请求地址

<https://open.oceanengine.com/open_api/oauth2/app_access_token/>
[可视化调试](https://open.oceanengine.com/tools/visual_debug.html?docId=1713655428885516)
[SDK下载](https://open.oceanengine.com/labels/7/docs/1773083358100557)
[MCP调用](https://open.oceanengine.com/labels/7/docs/1847394521222599)

# 请求方法

**POST**

# 请求Header

| 字段 | 类型 | 描述 |
| --- | --- | --- |
| Content-Type 必填 | string | 请求消息类型，允许值：`application/json` |

# 请求参数

| 字段 | 类型 | 描述 |
| --- | --- | --- |
| app\_id 必填 | number | 开发者申请的应用APP\_ID，可通过“[应用管理](https://open.oceanengine.com/developer/admin/ad_list/#/external/)”界面查看 |
| secret 必填 | string | 开发者应用的私钥Secret，可通过“[应用管理](https://open.oceanengine.com/developer/admin/ad_list/#/external/)”界面查看（确保填入secret与app\_id对应以免报错！） |

# 请求示例

**Python**

```python
def get_access_token():
    import requests
    open_api_url_prefix = "https://open.oceanengine.com/open_api/"
    uri = "oauth2/app_access_token/"
    url = open_api_url_prefix + uri
    data = {
        "app_id": 0,
        "secret": "xxx"
    }
    rsp = requests.post(url, json=data)
    rsp_data = rsp.json()
    return rsp_data
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
    private static final String PATH = "/open_api/oauth2/app_access_token/";
    private static final ObjectMapper mapper = new ObjectMapper();
​
    /**
     * Build request URL
     *
     * @param path Request path
     * @return Request URL
     */
    private static String buildUrl(String path) throws URISyntaxException {
        URI uri = new URI("https", "open.oceanengine.com", path, "", "");
        return uri.toString();
    }
​
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
                .build();
        Response response = client.newCall(request).execute();
        return response.body().string();
    }
​
    public static void main(String[] args) throws IOException, URISyntaxException {
        Long app_id = APP_ID;
        String secret = SECRET;
​
        // Args in JSON format
        String myArgs = String.format("{\"app_id\": \"%s\", \"secret\": \"%s\"}", app_id, secret);
        System.out.println(post(myArgs));
    }
}
```

---

**Php**

```php
$client = new http\Client;
$request = new http\Client\Request;
​
$body = new http\Message\Body;
$body-&gt;append('{
    "app_id": 0,
    "secret": ""
}');
​
$request-&gt;setRequestUrl('https://open.oceanengine.com/open_api/oauth2/app_access_token/');
$request-&gt;setRequestMethod('POST');
$request-&gt;setBody($body);
​
$request-&gt;setHeaders(array(
    'Content-Type' =&gt; 'application/json'
));
​
$client-&gt;enqueue($request)-&gt;send();
$response = $client-&gt;getResponse();
​
echo $response-&gt;getBody();
​
```

---

**Curl**

```bash
curl -X POST 'https://open.oceanengine.com/open_api/oauth2/app_access_token/' -H 'Content-Type: application/json' -d'
{
    "app_id": 0,
    "secret": ""
}
```

# 应答字段

| 字段 | 类型 | 描述 |
| --- | --- | --- |
| code | number | 返回码,详见[【附录-返回码】](https://open.oceanengine.com/labels/7/docs/1696710760866831) |
| message | string | 返回信息,详见[【附录-返回码】](https://open.oceanengine.com/labels/7/docs/1696710760866831) |
| data | json | json返回值 |
| access\_token | string | 应用级别token |
| expires\_in | number | access\_token剩余有效时间,单位(秒) |
| request\_id | string | 请求日志id |

# 应答示例

```
HTTPS/1.1 200 OK
{
   "code": 0,
   "message": "",
   "data": {
        "access_token": "",
        "expires_in": 86400
   }
}
```

