通过此接口，用户可以通过传入视频id和投放设置(setting)创建对应的前测任务

使用限制：

* 同一客户 1000素材/24H

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

<https://api.oceanengine.com/open_api/2/diagnosis_task/adv/create/>
[可视化调试](https://open.oceanengine.com/tools/visual_debug.html?docId=1816971004339210)
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
| advertiser\_id  必填 | number | 客户id |
| video\_ids | string[] | 视频id列表（长度限制100） |
| diagnose\_config | object | 前测setting |
| platform | string | 投放平台 可选值:    * `AD` AD * `QIANCHUAN` QIANCHUAN |
| external\_action | string | 转化目标 可选值:    * `AD_APP_ACTIVATE` AD：应用-激活 * `AD_APP_AUTH` AD：应用-授信 * `AD_APP_BOOK` AD：应用-预约表单 * `AD_APP_BUY` AD：应用-APP内付费 * `AD_APP_CLICKS` AD：应用-点击量 * `AD_APP_DETAIL` AD：应用-APP内详情页到站UV * `AD_APP_DOWNLOADED` AD：应用-下载完成 * `AD_APP_INSTALLED` AD：应用-安装完成 * `AD_APP_KEY_BEHAVIOR` AD：应用-关键行为 * `AD_APP_ORDER` AD：应用-APP内下单 * `AD_APP_PAY` AD：应用-付费 * `AD_APP_PRE_AUTH` AD：应用-预授信 * `AD_APP_PRE_DOWNLOAD` AD：应用-预约下载 * `AD_APP_PUSH_ORDER` AD：应用-首次发单(乘客) * `AD_APP_REGISTER` AD：应用-注册 * `AD_APP_SHOW` AD：应用-展示量 * `AD_APP_SUBMIT` AD：应用-提交认证 * `AD_APP_VIEW` AD：应用-APP内访问 * `AD_CLUE_AUTH` AD：销售线索收集-授信 * `AD_CLUE_BUTTON` AD：销售线索收集-按钮跳转 * `AD_CLUE_CLICKS` AD：销售线索收集-点击量 * `AD_CLUE_CONFIRM` AD：销售线索收集-回访-信息确认 * `AD_CLUE_CONSULT` AD：销售线索收集-有效咨询 * `AD_CLUE_CONSULT_MSG` AD：销售线索收集-留资咨询 * `AD_CLUE_COUPON` AD：销售线索收集-卡券领取 * `AD_CLUE_CUSTOMER` AD：销售线索收集-有效获客 * `AD_CLUE_CVT` AD：销售线索收集-多转化 * `AD_CLUE_DONE` AD：销售线索收集-完件 * `AD_CLUE_FORM` AD：销售线索收集-表单提交 * `AD_CLUE_FRIENDS` AD：销售线索收集-回访-加为好友 * `AD_CLUE_INSURANCE` AD：销售线索收集-保险支付 * `AD_CLUE_INTENTION` AD：销售线索收集-存在意向 * `AD_CLUE_INTENTION_FORM` AD：销售线索收集-意向表单 * `AD_CLUE_INTENTION_TEL` AD：销售线索收集-意向话单 * `AD_CLUE_MESSAGE` AD：销售线索收集-私信消息 * `AD_CLUE_MONEY` AD：销售线索收集-放款 * `AD_CLUE_MSG` AD：销售线索收集-私信留资 * `AD_CLUE_PAGE` AD：销售线索收集-访问目标页面 * `AD_CLUE_PAY` AD：销售线索收集-付费 * `AD_CLUE_PRE_AUTH` AD：销售线索收集-预授信 * `AD_CLUE_PROTENTIAL_DEAL` AD：销售线索收集-回访-高潜成交 * `AD_CLUE_PUSH_ORDER` AD：销售线索收集-首次发单（乘客） * `AD_CLUE_REGISTER` AD：销售线索收集-注册 * `AD_CLUE_SHOW` AD：销售线索收集-展示量 * `AD_CLUE_SUBMIT` AD：销售线索收集-提交认证 * `AD_CLUE_TEL` AD：销售线索收集-智能电话确认接通 * `AD_CLUE_TEL_CALL` AD：销售线索收集-电话接通 * `AD_CLUE_WX_ADD` AD：销售线索收集-微信-添加企业微信 * `AD_CLUE_WX_COPY` AD：销售线索收集-微信复制 * `AD_CLUE_WX_MSG` AD：销售线索收集-微信-用户首次消息 * `AD_ECP_APP_BUY` AD：电商-app内下单 * `AD_ECP_APP_DETAIL` AD：电商-app内详情页到站uv * `AD_ECP_APP_VIEW` AD：电商-app内访问 * `AD_ECP_BUTTON` AD：电商-按钮跳转 * `AD_ECP_INTEREST` AD：电商-引流电商种草 * `AD_ECP_SHOP` AD：电商-调起店铺 * `AD_ECP_SHOP_STAY` AD：电商-店铺停留 * `AD_MINIAPP_ACTIVATE` AD：快应用-激活 * `AD_MINIAPP_KEY_BEHAVIOR` AD：快应用-关键行为 * `AD_MINIAPP_PAY` AD：快应用-付费 * `AD_MINIAPP_REGISTER` AD：快应用-注册 * `AD_NATIVE_ACTIVATE` AD：原声互动-激活 * `AD_NATIVE_CLICKS` AD：原声互动-组件点击 * `AD_NATIVE_FANS_GROUP` AD：原声互动-粉丝入群 * `AD_NATIVE_FOLLOW` AD：原声互动-帐号关注 * `AD_NATIVE_INTERACTIVE` AD：原声互动-互动 * `AD_NATIVE_LIVE` AD：原声互动-预约直播 * `AD_NATIVE_LIVE_DONATE` AD：原声互动-直播间营销捐赠 * `AD_NATIVE_LIVE_PAY` AD：原声互动-直播间打赏 * `AD_NATIVE_LIVE_STAY` AD：原声互动-直播间停留 * `AD_NATIVE_LIVE_VIEW` AD：原声互动-直播间观看 * `AD_NATIVE_PAY` AD：原声互动-付费 * `AD_PRODUCT_ACTIVATE` AD：商品-激活 * `AD_PRODUCT_APP_BUY` AD：商品-app内下单 * `AD_PRODUCT_APP_DETAIL` AD：商品-app内详情页到站uv * `AD_PRODUCT_APP_PAY` AD：商品-app内付费 * `AD_PRODUCT_APP_VIEW` AD：商品-app内访问 * `AD_PRODUCT_FORM` AD：商品-表单提交 * `AD_PRODUCT_KEY_BEHAVIOR` AD：商品-关键行为 * `AD_PRODUCT_PAY` AD：商品-付费 * `AD_TINYAPP_ACTIVATE` 千川：小程序-激活 * `AD_TINYAPP_KEY_BEHAVIOR` 千川：小程序-关键行为 * `AD_TINYAPP_PAY` 千川：小程序-付费 * `QC_LIVE_BUY` 千川：直播投放-直播间下单 * `QC_LIVE_CHECK` 千川：直播投放-直播间结算 * `QC_LIVE_COMMENTS` 千川：直播投放-直播间评论 * `QC_LIVE_DEAL` 千川：直播投放-直播间成交 * `QC_LIVE_ENTRY` 千川：直播投放-进入直播间 * `QC_LIVE_FANS` 千川：直播投放-直播间粉丝提升 * `QC_LIVE_HIT` 千川：直播投放-直播加热 * `QC_LIVE_PRODUCT_CLICKS` 千川：直播投放-直播间商品点击 * `QC_LIVE_ROI_CHECK` 千川：直播投放-结算roi * `QC_LIVE_ROI_DEAL` 千川：直播投放-支付roi-直播间成交 * `QC_LIVE_ROI_QC` 千川：直播投放-支付roi-千川直接+间接订单 * `QC_PRODUCT_BUY` 千川：商品投放-商品购买 * `QC_PRODUCT_COMMENTS` 千川：商品投放-点赞评论 * `QC_PRODUCT_FANS` 千川：商品投放-粉丝提升 * `QC_PRODUCT_INTEREST` 千川：商品投放-人群种草 * `QC_PRODUCT_QC` 千川：商品投放-千川直接+间接订单 * `QC_PRODUCT_ROI` 千川：商品投放-商品支付roi |
| cpa\_bid | double | 目标转化成本：取值范围: [1, 10000], 精确到小数点后2位 |
| audience\_gender | string | 性别 可选值:    * `ALL` 不限 * `MALE` 男 * `FEMALE` 女 |
| audience\_age | string[] | 受众年龄 可选值:    * `ALL` 不限 * `18-23` 18-23 * `24-30` 24-30 * `31-40` 31-40 * `41-49` 41-49 * `50` 50+ |
| audience\_region | number[] | 受众地区，传入二级行政区域（市）的code，行政区域接口 |
| audience\_network | string[] | 网络类型 可选值:    * `ALL` 不限 * `5G` 5G * `4G` 4G * `3G` 3G * `2G` 2G * `WIFI` wifi |
| cus\_name | string | 客户主体名称 |
| pricing\_type | string | 可选值:    * `OCPC` ocpc * `CPA` cpa * `OCPM` ocpm |
| cost\_cap | bool | 是否最优成本出价，只有AD支持，千川场景下会忽略本字段 |
| target\_cost | bool | 是否稳定成本出价，只有AD支持，千川场景下会忽略本字段 |
| nobid | bool | 是否最大转化出价，只有AD支持，千川场景下会忽略本字段 |
| cpc\_bid | double | 目标点击成本：取值范围: [1, 10000], 精确到小数点后2位 |
| budget | double | 预算金额：取值范围: [1, 10000], 精确到小数点后2位 |
| ref\_ad\_id | number | 参考营销id，可复用该营销id的setting进行前测，非空情况下会忽略diagnose\_config。 和ref\_promotion\_id二选一 |
| ref\_promotion\_id | number | 参考营销id，可复用该营销id的setting进行前测，非空情况下会忽略diagnose\_config。 和ref\_ad\_id二选一 |

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
PATH = "/open_api/2/diagnosis_task/adv/create/"
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
    video_ids_list = VIDEO_IDS
    video_ids = json.dumps(video_ids_list)
    platform = PLATFORM
    external_action = EXTERNAL_ACTION
    cpa_bid = CPA_BID
    audience_gender = AUDIENCE_GENDER
    audience_age_list = AUDIENCE_AGE
    audience_age = json.dumps(audience_age_list)
    audience_region_list = AUDIENCE_REGION
    audience_region = json.dumps(audience_region_list)
    audience_network_list = AUDIENCE_NETWORK
    audience_network = json.dumps(audience_network_list)
    cus_name = CUS_NAME
    pricing_type = PRICING_TYPE
    cost_cap = COST_CAP
    target_cost = TARGET_COST
    nobid = NOBID
    cpc_bid = CPC_BID
    budget = BUDGET
    ref_ad_id = REF_AD_ID
    ref_promotion_id = REF_PROMOTION_ID
​
    # Args in JSON format
    my_args = "{\"advertiser_id\": \"%s\", \"video_ids\": %s, \"diagnose_config\": {\"platform\": \"%s\", \"external_action\": \"%s\", \"cpa_bid\": \"%s\", \"audience_gender\": \"%s\", \"audience_age\": %s, \"audience_region\": %s, \"audience_network\": %s, \"cus_name\": \"%s\", \"pricing_type\": \"%s\", \"cost_cap\": \"%s\", \"target_cost\": \"%s\", \"nobid\": \"%s\", \"cpc_bid\": \"%s\", \"budget\": \"%s\"}, \"ref_ad_id\": \"%s\", \"ref_promotion_id\": \"%s\"}" % (advertiser_id, video_ids, platform, external_action, cpa_bid, audience_gender, audience_age, audience_region, audience_network, cus_name, pricing_type, cost_cap, target_cost, nobid, cpc_bid, budget, ref_ad_id, ref_promotion_id)
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
    private static final String PATH = "/open_api/2/diagnosis_task/adv/create/";
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
        List < String > video_ids_list = VIDEO_IDS;
        String video_ids = mapper.writeValueAsString(video_ids_list);
        String platform = PLATFORM;
        String external_action = EXTERNAL_ACTION;
        String cpa_bid = CPA_BID;
        String audience_gender = AUDIENCE_GENDER;
        List < String > audience_age_list = AUDIENCE_AGE;
        String audience_age = mapper.writeValueAsString(audience_age_list);
        List < Long > audience_region_list = AUDIENCE_REGION;
        String audience_region = mapper.writeValueAsString(audience_region_list);
        List < String > audience_network_list = AUDIENCE_NETWORK;
        String audience_network = mapper.writeValueAsString(audience_network_list);
        String cus_name = CUS_NAME;
        String pricing_type = PRICING_TYPE;
        String cost_cap = COST_CAP;
        String target_cost = TARGET_COST;
        String nobid = NOBID;
        String cpc_bid = CPC_BID;
        String budget = BUDGET;
        Long ref_ad_id = REF_AD_ID;
        Long ref_promotion_id = REF_PROMOTION_ID;
​
        // Args in JSON format
        String myArgs = String.format("{\"advertiser_id\": \"%s\", \"video_ids\": %s, \"diagnose_config\": {\"platform\": \"%s\", \"external_action\": \"%s\", \"cpa_bid\": \"%s\", \"audience_gender\": \"%s\", \"audience_age\": %s, \"audience_region\": %s, \"audience_network\": %s, \"cus_name\": \"%s\", \"pricing_type\": \"%s\", \"cost_cap\": \"%s\", \"target_cost\": \"%s\", \"nobid\": \"%s\", \"cpc_bid\": \"%s\", \"budget\": \"%s\"}, \"ref_ad_id\": \"%s\", \"ref_promotion_id\": \"%s\"}",advertiser_id, video_ids, platform, external_action, cpa_bid, audience_gender, audience_age, audience_region, audience_network, cus_name, pricing_type, cost_cap, target_cost, nobid, cpc_bid, budget, ref_ad_id, ref_promotion_id);
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
$PATH = "/open_api/2/diagnosis_task/adv/create/";
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
$video_ids_list = VIDEO_IDS;
$video_ids = json_encode($video_ids_list);
$platform = PLATFORM;
$external_action = EXTERNAL_ACTION;
$cpa_bid = CPA_BID;
$audience_gender = AUDIENCE_GENDER;
$audience_age_list = AUDIENCE_AGE;
$audience_age = json_encode($audience_age_list);
$audience_region_list = AUDIENCE_REGION;
$audience_region = json_encode($audience_region_list);
$audience_network_list = AUDIENCE_NETWORK;
$audience_network = json_encode($audience_network_list);
$cus_name = CUS_NAME;
$pricing_type = PRICING_TYPE;
$cost_cap = COST_CAP;
$target_cost = TARGET_COST;
$nobid = NOBID;
$cpc_bid = CPC_BID;
$budget = BUDGET;
$ref_ad_id = REF_AD_ID;
$ref_promotion_id = REF_PROMOTION_ID;
​
/* Args in JSON format */
$my_args = sprintf("{\"advertiser_id\": \"%s\", \"video_ids\": %s, \"diagnose_config\": {\"platform\": \"%s\", \"external_action\": \"%s\", \"cpa_bid\": \"%s\", \"audience_gender\": \"%s\", \"audience_age\": %s, \"audience_region\": %s, \"audience_network\": %s, \"cus_name\": \"%s\", \"pricing_type\": \"%s\", \"cost_cap\": \"%s\", \"target_cost\": \"%s\", \"nobid\": \"%s\", \"cpc_bid\": \"%s\", \"budget\": \"%s\"}, \"ref_ad_id\": \"%s\", \"ref_promotion_id\": \"%s\"}", $advertiser_id, $video_ids, $platform, $external_action, $cpa_bid, $audience_gender, $audience_age, $audience_region, $audience_network, $cus_name, $pricing_type, $cost_cap, $target_cost, $nobid, $cpc_bid, $budget, $ref_ad_id, $ref_promotion_id);
echo post($my_args);
​
```

---

**Curl**

```bash
curl -H "Access-Token:xxx" -H "Content-Type:application/json" -X POST \
-d '{
    "advertiser_id": "ADVERTISER_ID",
    "video_ids": [
        "VIDEO_IDS"
    ],
    "diagnose_config": {
        "platform": "PLATFORM",
        "external_action": "EXTERNAL_ACTION",
        "cpa_bid": "CPA_BID",
        "audience_gender": "AUDIENCE_GENDER",
        "audience_age": [
            "AUDIENCE_AGE"
        ],
        "audience_region": [
            "AUDIENCE_REGION"
        ],
        "audience_network": [
            "AUDIENCE_NETWORK"
        ],
        "cus_name": "CUS_NAME",
        "pricing_type": "PRICING_TYPE",
        "cost_cap": "COST_CAP",
        "target_cost": "TARGET_COST",
        "nobid": "NOBID",
        "cpc_bid": "CPC_BID",
        "budget": "BUDGET"
    },
    "ref_ad_id": "REF_AD_ID",
    "ref_promotion_id": "REF_PROMOTION_ID"
}' \
https://api.oceanengine.com/open_api/2/diagnosis_task/adv/create/
```

# 应答字段

| 字段 | 类型 | 描述 |
| --- | --- | --- |
| code | number | 返回码,详见 [【附录-返回码】](https://open.oceanengine.com/labels/7/docs/1696710760866831) |
| message | string | 返回信息,详见 [【附录-返回码】](https://open.oceanengine.com/labels/7/docs/1696710760866831) |
| data | json | json返回值 |
| task\_ids | number[] | 成功创建的前测任务id |
| fail\_video\_ids | dict[object] | 创建失败的视频id |
| err\_code | string | 创建失败的code |
| err\_message | string | 创建失败的原因 |
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

