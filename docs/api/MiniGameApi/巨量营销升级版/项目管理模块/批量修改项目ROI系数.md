本接口支持批量修改项目ROI系数，当前仅以下项目支持ROI系数修改：

1. 应用、自动投放项目
2. 电商、自动投放项目
3. 电商、自动投放、周期稳投项目
4. 小程序、自动投放项目

关键信息

详情

是否支持SDK

支持

权限点及应用类型

了解如何 [申请授权&生成授权](https://open.oceanengine.com/labels/7/docs/1803016515293203?origin=metadata)

权限点:  投放管理-项目列表-项目创编

应用类型:  自研投放应用-客户/代理商/独立三方站点/群峰上架服务、提供第三方服务-客户/代理商/独立三方站点/群峰上架服务

接入能力范围:  巨量 PC

支持的账户类型

客户投放账户

# 请求地址

<https://api.oceanengine.com/open_api/v3.0/project/roigoal/update/>
[可视化调试](https://open.oceanengine.com/tools/visual_debug.html?docId=1794208148473859)
[SDK下载](https://open.oceanengine.com/labels/7/docs/1773083358100557)
[MCP调用](https://open.oceanengine.com/labels/7/docs/1847394521222599)

# 请求方法

POST

# Header

| 字段 | 类型 | 描述 |
| --- | --- | --- |
| Access-Token  必填 | string | 授权access\_token，可以通过【[获取Access token](https://open.oceanengine.com/labels/7/docs/1696710505596940)】接口获取 |
| Content-Type  必填 | string | 请求消息类型 允许值: `application/json` |

# 请求参数

| 字段 | 类型 | 描述 |
| --- | --- | --- |
| advertiser\_id  必填 | number | 投放账户id |
| data  必填 | object[] | 批量修改项目ROI系数，list长度限制10 |
| project\_id  必填 | number | 项目ID |
| roi\_goal  必填 | float | 深度转化ROI系数，填写要求如下：   1. 应用、自动投放项目，ROI系数范围[0.01,5]，仅支持最多4位小数 2. 电商投放、自动投放项目，ROI系数范围[0.01,100]，仅支持最多4位小数 3. 电商投放、自动投放、周期稳投项目，ROI系数只允许调小且新建7天内每自然日最多允许成功修改1次 4. 小程序、自动投放项目，ROI系数范围[0.01,5]，仅支持最多4位小数 |
| shop\_multi\_roi\_goals | object[] | 电商平台多ROI系数设置，引流电商多平台投放ROI系数及平台信息，可按照电商平台分别确定ROI系数，分平台调控出价，此能力白名单开放。list长度最长为4  填写条件：仅当满足以下5个条件时可传入，此时无需传入roi\_goal参数：   1. landing\_type = SHOP电商 2. delivery\_mode = PROCEDURAL自动投放 3. external\_action = AD\_CONVERT\_TYPE\_APP\_ORDER APP内下单 4. deep\_bid\_type = ROI\_DIRECT\_MAILROI直投 5. 投放账户已经开通多ROI投放白名单，如有疑问请联系对接销售/运营   填写要求：   * 长度1-4 * 单ROI（仅设置roi\_goal）和多ROI项目（仅设置shop\_multi\_roi\_goals）不支持同时传入修改 |
| roi\_goal | double | ROI系数值，范围[0.01,100]，精度：最多保留小数点后四位 |
| shop\_platform | string | 可选值:    * `JD` 京东 * `OTHER` 其他 * `PDD` 拼多多 * `TB` 淘宝 |

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
PATH = "/open_api/v3.0/project/roigoal/update/"
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
    advertiser_id = ADVERTISER_ID
    project_id = PROJECT_ID
    roi_goal = ROI_GOAL
    roi_goal = ROI_GOAL
    shop_platform = SHOP_PLATFORM
​
    # Args in JSON format
    my_args = "{\"advertiser_id\": \"%s\", \"data\": [{\"project_id\": \"%s\", \"roi_goal\": \"%s\", \"shop_multi_roi_goals\": [{\"roi_goal\": \"%s\", \"shop_platform\": \"%s\"}]}]}" % (advertiser_id, project_id, roi_goal, roi_goal, shop_platform)
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
    private static final String PATH = "/open_api/v3.0/project/roigoal/update/";
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
        Long advertiser_id = ADVERTISER_ID;
        Long project_id = PROJECT_ID;
        String roi_goal = ROI_GOAL;
        String roi_goal = ROI_GOAL;
        String shop_platform = SHOP_PLATFORM;
​
        // Args in JSON format
        String myArgs = String.format("{\"advertiser_id\": \"%s\", \"data\": [{\"project_id\": \"%s\", \"roi_goal\": \"%s\", \"shop_multi_roi_goals\": [{\"roi_goal\": \"%s\", \"shop_platform\": \"%s\"}]}]}",advertiser_id, project_id, roi_goal, roi_goal, shop_platform);
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
$PATH = "/open_api/v3.0/project/roigoal/update/";
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
$advertiser_id = ADVERTISER_ID;
$project_id = PROJECT_ID;
$roi_goal = ROI_GOAL;
$roi_goal = ROI_GOAL;
$shop_platform = SHOP_PLATFORM;
​
/* Args in JSON format */
$my_args = sprintf("{\"advertiser_id\": \"%s\", \"data\": [{\"project_id\": \"%s\", \"roi_goal\": \"%s\", \"shop_multi_roi_goals\": [{\"roi_goal\": \"%s\", \"shop_platform\": \"%s\"}]}]}", $advertiser_id, $project_id, $roi_goal, $roi_goal, $shop_platform);
echo post($my_args);
​
```

---

**Curl**

```bash
curl -H "Access-Token:xxx" -H "Content-Type:application/json" -X POST \
-d '{
    "advertiser_id": "ADVERTISER_ID",
    "data": [
        {
            "project_id": "PROJECT_ID",
            "roi_goal": "ROI_GOAL",
            "shop_multi_roi_goals": [
                {
                    "roi_goal": "ROI_GOAL",
                    "shop_platform": "SHOP_PLATFORM"
                }
            ]
        }
    ]
}' \
https://api.oceanengine.com/open_api/v3.0/project/roigoal/update/
```

# 应答字段

| 字段 | 类型 | 描述 |
| --- | --- | --- |
| code | number | 返回码,详见 [【附录-返回码】](https://open.oceanengine.com/labels/7/docs/1696710760866831) |
| message | string | 返回信息,详见 [【附录-返回码】](https://open.oceanengine.com/labels/7/docs/1696710760866831) |
| data | json | json返回值 |
| project\_ids | number[] | 更新成功的项目ID列表 |
| errors | object[] | 更新失败的项目ID列表及失败原因 |
| project\_id | number | 项目ID |
| error\_message | string | 错误信息 |
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

