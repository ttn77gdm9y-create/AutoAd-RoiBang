Adv获取前测任务列表

关键信息

详情

是否支持SDK

支持

权限点及应用类型

了解如何 [申请授权&生成授权](https://open.oceanengine.com/labels/7/docs/1803016515293203?origin=metadata)

权限点:  工具-审核查询工具-素材前测工具

应用类型:  自研投放应用-客户/代理商/独立三方站点/群峰上架服务、提供第三方服务-客户/代理商/独立三方站点/群峰上架服务

接入能力范围:  巨量 PC

支持的账户类型

客户投放账户

# 请求地址

<https://api.oceanengine.com/open_api/2/diagnosis_task/adv/list/>
[可视化调试](https://open.oceanengine.com/tools/visual_debug.html?docId=1816971069170691)
[SDK下载](https://open.oceanengine.com/labels/7/docs/1773083358100557)
[MCP调用](https://open.oceanengine.com/labels/7/docs/1847394521222599)

# 请求方法

GET

# Header

| 字段 | 类型 | 描述 |
| --- | --- | --- |
| Access-Token  必填 | string | 授权access\_token，可以通过【[获取Access token](https://open.oceanengine.com/labels/7/docs/1696710505596940)】接口获取 |

# 请求参数

| 字段 | 类型 | 描述 |
| --- | --- | --- |
| advertiser\_id | number | 客户id |
| results | string[] | 根据任务结果筛选 允许值：   * `AD_HIGH_QUALITY_MATERIAL` AD优质素材 * `ECP_HIGH_QUALITY_MATERIAL` 千川优质素材 * `FIRST_PUBLISH_MATERIAL` 首发素材 * `INEFFICIENT_MATERIAL` 低效素材 * `NON_AD_HIGH_QUALITY_MATERIAL` AD非优质素材 * `NON_ECP_HIGH_QUALITY_MATERIAL` 千川非优质素材 * `NON_FIRST_PUBLISH_MATERIAL` 非首发素材 * `NON_INEFFICIENT_MATERIAL` 非低效素材 |
| status | string[] | 可选值:    * `FAILED` * `PENDING` * `SUCCESS` |
| start\_time | number | 根据任务创建时间进行过滤的起始时间，与end\_time搭配使用，格式：秒级时间戳 |
| end\_time | number | 根据任务创建时间进行过滤的截止时间，与start\_time搭配使用，格式：秒级时间戳  start\_time和end\_time 时间跨度最大30天 |
| page | number | 页码 |
| page\_size | number | 页面大小，默认值20，最大100 |

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
PATH = "/open_api/2/diagnosis_task/adv/list/"
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
    advertiser_id = ADVERTISER_ID
    results_list = RESULTS
    results = json.dumps(results_list)
    status_list = STATUS
    status = json.dumps(status_list)
    start_time = START_TIME
    end_time = END_TIME
    page = PAGE
    page_size = PAGE_SIZE
​
    # Args in JSON format
    my_args = "{\"advertiser_id\": \"%s\", \"results\": %s, \"status\": %s, \"start_time\": \"%s\", \"end_time\": \"%s\", \"page\": \"%s\", \"page_size\": \"%s\"}" % (advertiser_id, results, status, start_time, end_time, page, page_size)
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
    private static final String PATH = "/open_api/2/diagnosis_task/adv/list/";
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
        Long advertiser_id = ADVERTISER_ID;
        List < String > results_list = RESULTS;
        String results = mapper.writeValueAsString(results_list);
        List < String > status_list = STATUS;
        String status = mapper.writeValueAsString(status_list);
        Long start_time = START_TIME;
        Long end_time = END_TIME;
        Long page = PAGE;
        Long page_size = PAGE_SIZE;
​
        // Args in JSON format
        String myArgs = String.format("{\"advertiser_id\": \"%s\", \"results\": %s, \"status\": %s, \"start_time\": \"%s\", \"end_time\": \"%s\", \"page\": \"%s\", \"page_size\": \"%s\"}",advertiser_id, results, status, start_time, end_time, page, page_size);
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
$PATH = "/open_api/2/diagnosis_task/adv/list/";
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
$advertiser_id = ADVERTISER_ID;
$results_list = RESULTS;
$results = json_encode($results_list);
$status_list = STATUS;
$status = json_encode($status_list);
$start_time = START_TIME;
$end_time = END_TIME;
$page = PAGE;
$page_size = PAGE_SIZE;
​
/* Args in JSON format */
$my_args = sprintf("{\"advertiser_id\": \"%s\", \"results\": %s, \"status\": %s, \"start_time\": \"%s\", \"end_time\": \"%s\", \"page\": \"%s\", \"page_size\": \"%s\"}", $advertiser_id, $results, $status, $start_time, $end_time, $page, $page_size);
echo get($my_args);
​
```

---

**Curl**

```bash
curl --get -H "Access-Token:xxx" \
--data-urlencode "advertiser_id=ADVERTISER_ID" \
--data-urlencode "results=[\"RESULTS\"]" \
--data-urlencode "status=[\"STATUS\"]" \
--data-urlencode "start_time=START_TIME" \
--data-urlencode "end_time=END_TIME" \
--data-urlencode "page=PAGE" \
--data-urlencode "page_size=PAGE_SIZE" \
https://api.oceanengine.com/open_api/2/diagnosis_task/adv/list/
```

# 应答字段

| 字段 | 类型 | 描述 |
| --- | --- | --- |
| code | number | 返回码,详见 [【附录-返回码】](https://open.oceanengine.com/labels/7/docs/1696710760866831) |
| message | string | 返回信息,详见 [【附录-返回码】](https://open.oceanengine.com/labels/7/docs/1696710760866831) |
| data | json | json返回值 |
| task\_list | object[] | 任务列表 |
| task\_id  必填 | number | 任务id |
| status  必填 | string | 可选值:    * `FAILED` * `PENDING` * `SUCCESS` |
| video\_id  必填 | string | 视频id |
| advertiser\_id | number | 客户id |
| material\_id | number | 素材id |
| is\_ad\_high\_quality\_material | string | 可选值:    * `NO` * `UNKNOWN` * `YES` |
| is\_ecp\_high\_quality\_material | string | 可选值:    * `NO` * `UNKNOWN` * `YES` |
| is\_inefficient\_material | string | 可选值:    * `NO` * `UNKNOWN` * `YES` |
| is\_first\_publish\_material | string | 可选值:    * `NO` * `UNKNOWN` * `YES` |
| not\_ad\_high\_quality\_reason | string[] | AD非优质原因 |
| not\_ecp\_high\_quality\_reason | string[] | 千川非优质原因 |
| page\_info | object | 分页信息 |
| page | number | 页码 |
| page\_size | number | 分页大小 |
| total\_number | number | 总数 |
| total\_page | number | 总页数 |
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

