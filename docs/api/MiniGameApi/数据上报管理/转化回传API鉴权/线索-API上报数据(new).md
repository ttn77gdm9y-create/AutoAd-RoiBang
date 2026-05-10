## 使用场景

采用该方式追踪时，巨量引擎会在您的落地页链接上拼接参数，您将符合转化条件的用户参数进行回传，完成转化上报，追踪落地页转化效果。推荐使用场景：用户转化行为不在落地页完成（例如用户提交电话号码后，客户电话回访后标记出有效用户）

## 流程说明

### 1、整体流程

用户点击营销时，打开的落地页链接上会带有宏替换后的检测参数，即实际的ad\_id、creative\_id、promotion\_id、project\_id、creative\_type、clickid等。客户的服务端根据落地页请求日志，将拼接了参数的落地页url和用户线索做映射，例如用户A、B、C均在页面上提交了表单，其中用户A对应url 1，用户B对应url 2，用户C对应url3。经过电话回访，三人中B用户为有意向的高价值用户，则将B用户的url2发送到巨量引擎回传地址上，记为转化用户。

### 2、监测参数

形如`adid=__AID__&creativeid=__CID__&creativetype=__CTYPE__&click__id=__CLICKID__`，您在营销计划中填写落地页链接后，巨量引擎会自动为您添加该参数，并在投放过程中为宏参数赋值。其中下划线的部分，就是我们替换后的真实营销信息（非 ASCII 字符，进行了 url encode）。其形态在投放1.0和投放2.0场景下，有所区分，示例如下：

* 在投放1.0场景下，形如：

```
adid=__AID__&creativeid=__CID__&creativetype=__CTYPE__&clickid=__CLICKID__
```

-在投放2.0场景下，形如：

```
projectid=__PROJECT_ID__&promotionid=__PROMOTION_ID__&creativetype=__CTYPE__&clickid=__CLICKID__
```

假设客户收到的真实请求，

* 在投放1.0场景下，示例如下：

```
https://mybest.custom.com/click/?adid=123123123123&cretiveid=321321321321&creativetype=2&clickid=CJPAgsnOmvcCELSYmfnRmvcCGIWf9-fuASCr49bD9wEojtjvjYWV9wIwDDix6gFCIjIwMTkxMjAyMTkwODQ5MDEwMDE0MDQzMjI1MDI3MzVCQzNIseoBULHqAQ==
```

* 在投放2.0场景下，示例如下：

```
https://mybest.custom.com/click/?projectid=7074806092097929253&promotionid=7074140945750507528&creativetype=2&clickid=CJPAgsnOmvcCELSYmfnRmvcCGIWf9-fuASCr49bD9wEojtjvjYWV9wIwDDix6gFCIjIwMTkxMjAyMTkwODQ5MDEwMDE0MDQzMjI1MDI3MzVCQzNIseoBULHqAQ==
```

**落地页参数说明：**

| 宏 | 适用场景 | 含义 | 举例 |
| --- | --- | --- | --- |
| AID | 仅投放1.0 | 营销计划id | 样例：1645988237525045 |
| CID | 仅投放1.0 | 营销创意 id，长整型 | 样例：1650703686054530 |
| PROMOTION\_ID | 仅投放2.0 | 投放2.0中特有的宏参，代表投放2.0的营销ID | 样例：7074140945750507528 |
| PROJECT\_ID | 仅投放2.0 | 投放2.0中特有的宏参，代表投放2.0的项目ID | 样例：7074806092097929253 |
| CTYPE | 可兼容支持 | 创意样式 | 2=小图模式；3=大图模式；4=组图模式；5=视频 |
| CLICKID | 可兼容支持 | 标记每一次点击的唯一标识 | 样例:CJPAgsnOmvcCELSYmfnRmvcCGIWf9-fuASCr49bD9wEojtjvjYWV9wIwDDix6gFCIjIwMTkxMjAyMTkwODQ5MDEwMDE0MDQzMjI1MDI3MzVCQzNIseoBULHqAQ== |

### 3、数据回传

用于客户将转化用户实时上报给巨量引擎服务器，巨量引擎会将转化用户与营销计划关联，跟踪每个营销计划的转化效果。

#### 接口地址

```
https://ad.oceanengine.com/track/activate/?link=__LINK__&source=__SOURCE__&conv_time=__CONVTIME__&event_type=__EVENT_TYPE__
```

#### 通信协议

支持通过HTTPS通道进行请求通信。为了获得更高的安全性，推荐您使用HTTPS通道发送请求。

#### 请求方法

支持HTTPS GET方法发送请求，这种方式下请求参数需要包含在请求的URL中。

#### 字符编码

统一采用 UTF-8 的编码格式，url 中的参数如果包含非 ASC 字符，需要进行 url encode 传递。假如我们需要传入一个字段，props = {"aaa":"bbb"}，我们需要对 json 字符串进行 encode

```
https://ad.oceanengine.com/track/activate/?link=https://mybestcustom.com/index.html?adid= 123123123123&creativeid=321321321321&creativetype=2&clickid= CJPAgsnOmvcCELSYmfnRmvcCGIWf9fuASCr49bD9wEojtjvjYWV9wIwDDix6gFCIjIwMTkxMjAyMTkwODQ5MDEwMDE0MDQzMjI1MDI3MzVCQzNIseoBULHqAQ==&event_type=3
```

#### 回传参数说明：

**link （必填）**

link字段就是营销被打开的落地页的原始真实 url，客户需要把这个 url ，encode 之后传递给巨量引擎。

举例说明：

（1）客户在营销投放平台填写落地页链接

`https://mybestcustom.com/index.html`

（2）用户在信息流中打开这个页面后，巨量引擎会在页面的后面添加上几个跟营销相关的参数，url 会变成

```
https://mybest.custom.com/click/?aid=123123123123&cretiveid=321321321321&creativetype=2&clickid=CJPAgsnOmvcCELSYmfnRmvcCGIWf9-fuASCr49bD9wEojtjvjYWV9wIwDDix6gFCIjIwMTkxMjAyMTkwODQ5MDEwMDE0MDQzMjI1MDI3MzVCQzNIseoBULHqAQ==
```

（3）客户在响应到这个页面打开之后需要把这个完整的 url，encode之后 传递给巨量引擎。

```
encodeURIComponent('https://mybestcustom.com/index.html?adid=123123123123&creativeid= 321321321321&creativetype=2&clickid=CJPAgsnOmvcCELSYmfnRmvcCGIWf9fuASCr49bD9wEojtjvjYWV9wIwDDix6gFCIjIwMTkxMjAyMTkwODQ5MDEwMDE0MDQzMjI1MDI3MzVCQzNIseoBULHqAQ==') =
https://mybestcustom.com/index.html?adid=123123123123&creativeid=321321321321&creativetype=2&clickid=CJPAgsnOmvcCELSYmfnRmvcCGIWf9fuASCr49bD9wEojtjvjYWV9wIwDDix6gFCIjIwMTkxMjAyMTkwODQ5MDEwMDE0MDQzMjI1MDI3MzVCQzNIseoBULHqAQ==
```

（4）最终调用我们的回传接口时，参数是

```
https://ad.oceanengine.com/track/activate/?link=https://mybestcustom.com/index.html?adid= 123123123123&creativeid=321321321321&creativetype=2&clickid= CJPAgsnOmvcCELSYmfnRmvcCGIWf9fuASCr49bD9wEojtjvjYWV9wIwDDix6gFCIjIwMTkxMjAyMTkwODQ5MDEwMDE0MDQzMjI1MDI3MzVCQzNIseoBULHqAQ==&event_type=3
```

**Event\_type（必填回传参数）**

event\_type 代表的是事件类型，这个值是一个数字类型枚举值，如果回传的值既不在枚举范围内，也未曾与巨量引擎进行其他形式的确认，巨量引擎将无法识别具体事件类型。具体取值如下：

| 取值 | 事件名称 | 定义 |
| --- | --- | --- |
| 2 | 付费 | 用户在投放的落地页场景下发生交易并完成至少一笔付款，具体支付形式取决于客户业务模式 |
| 3 | 表单 | 页面内完成表单填写并提交 |
| 5 | 有效咨询 | 点击页面“在线咨询”，且在咨询对话框中内容达到≥1条以上对话记录的，记录一次转化。客户可自定义有效的标准。 |
| 7 | 电话拨打 | 用户点击拨打电话 |
| 19 | 有效获客 | 用户完成了一次有价值的动作，如预约到店，完成授权等，支持客户根据业务场景自定义 |
| 194 | 回访\_信息确认 | 线索经联系确认是本人提交的信息，或者是本人有初步意向了解 |
| 195 | 回访\_加为好友 | 线索和销售建立了交流，比如互加好友，建立联系，可以持续跟进 |
| 196 | 回访\_高潜成交 | 线索有较强意向成交或者处于成交流程，尚未完结 |
| 218 | 支付\_存在意向 | 在落地页完成的在线支付成功行为 |
| 386 | 微信\_添加企业微信 | 用户扫描二维码，成功添加商家的企业微信 |
| 387 | 微信\_用户首次消息 | 用户添加企业微信后，首次发起消息，开口咨询 |
| 388 | 微信\_用户首次消息 | 添加企业微信后，用户在首次消息之后，又表明确定有需求意向或产品意向 |
| 396 | 企业微信\_取消好友 | 用户取消和营销客户员工企业微信的好友关系 |

**回传其他参数**

| 参数 | 格式 | 是否必填 | 描述 |  |
| --- | --- | --- | --- | --- |
| conv\_time | int（整型） | 建议填写 | UTC 时间戳，单位：秒 |  |
| source | string（字符串） | 建议填写 | 数据来源，比如来自 talkingdata的激活回调, 可以填写 TD |  |

#### 回传调用示例

Golang

Nodejs

Java

PHP

Python

func Send() error {
url := "https://ad.oceanengine.com/track/activate/"
req, err := http.NewRequest(http.MethodGet, url, nil)
if err != nil {
log.Println(err)
return nil, errors.New("new request is fail ")
}
q := req.URL.Query()
q.Add("callback","EJiw267wvfQCGKf2g74ZIPD89-vIATAMOAFCIjIwMTkxMTI3MTQxMTEzMDEwMDI2MDc3MjE1MTUwNTczNTBIAQ==")
q.Add("imei","0c2bd03c39f19845bf54ea0abafae70e")
q.Add("event\_type",10)
q.Add("conv\_time", 1574758519)
req.URL.RawQuery = q.Encode()
client := &http.Client{}
return client.Do(req)
}

### 4、联调步骤

联调目的在于确保您正确调用了回传地址，能够将转化用户进行回传

#### 4.1 填写落地页

填写转化名称，输入落地页链接，并选择转化目标，以“有效获客”为例，此处转化目标选择为“有效获客”。提交后进入下一步

![xiansuo_API_pic1.png](https://p3-business-sign.byteadimg.com/tos-cn-i-yvqzo4lhg5/8d520dd7c7fe4c86932e542affcf3da8~noop.image?x-expires=1988788630&x-signature=wPR2yQ9muP8D0WTuNyIJn1NsYnY%3D "xiansuo_API_pic1.png")

**点击监测链接**

线索API，点击监测链接为非必填项

点击监测链接详情可戳：<https://ad.oceanengine.com/openapi/doc/index.html?id=1696710655781900>

#### 4.2 确认信息

1.确认基本信息是否填写正确，若填写正确，则确认激活状态

2.如果输入的落地页链接对应的域名在同一个客户id下联调成功过，则此处直接免联调。此处仍建议客户确认下是否能够正常回传转化事件

3.若未免联调，即转化状态处于“未激活”状态，点击“检测转化上报”，开始联调

![xiansuo_API_pic2.png](https://p26-business-sign.byteadimg.com/tos-cn-i-yvqzo4lhg5/6c3c6e129afb4efa818d95ef2ba8e3cf~noop.image?x-expires=1988788630&x-signature=m7jdA%2BzIMAv7hp00gO6o7y6QAUA%3D "xiansuo_API_pic2.png")

下图是免联调界面 ![xiansuo_API_pic3.png](https://p3-business-sign.byteadimg.com/tos-cn-i-yvqzo4lhg5/2d9149dc7c06454d97b294c73df37564~noop.image?x-expires=1988788630&x-signature=6WaoFdeeGsO2GhsT72bFIl1k6%2B4%3D "xiansuo_API_pic3.png")

#### 4.3 开始联调

此处支持两种联调方案：

**方案一**：（推荐使用该方案）

（1）营销投放时，平台将以下参数拼接在您的落地页链接上并赋值，需技术人员将落地页链接与线索做映射，例：A用户对应URL1，B用户对应URL2，C用户对应URL3。

（2）将符合转化条件的线索信息回传到以下地址（[https://ad.oceanengine.com/track/activate/?link=**LINK**&source=**SOURCE**&conv\_time=**CONVTIME**&event\_type=**EVENT\_TYPE**](https://ad.oceanengine.com/track/activate/?link=__LINK__&source=__SOURCE__&conv_time=__CONVTIME__&event_type=__EVENT_TYPE__)），其中参数“\_\_LINK\_\_”需填入目标线索映射的URL。例：A、B、C三个用户中，B符合您定义的转化条件，则将B用户对应的URL回传。

**方案二**（仍支持原来的联调方案，即解析并回传clickid）：

（1）营销投放时，平台将以下参数拼接在您的落地页链接上并赋值，需技术人员解析出落地页链接中拼接的clickid，并将clickid与线索做映射，例：A用户对应clickid1，B用户对应clickid2，C用户对应clickid3。

（2）将符合转化条件的线索信息回传到以下地址（[http://ad.oceanengine.com/track/activate/?callback=**CLICKID**&source=**SOURCE**&conv\_time=**CONV\_TIME**&event\_type=**EVENT\_TYPE**](http://ad.oceanengine.com/track/activate/?callback=__CLICKID__&source=__SOURCE__&conv_time=__CONV_TIME__&event_type=__EVENT_TYPE__)），其中参数“\_\_CLICKID\_\_”需填入目标线索映射的clickid。例：A、B、C三个用户中，B符合您定义的转化条件，则将B用户对应的clickid回传

![xiansuo_API_pic4.png](https://p6-business-sign.byteadimg.com/tos-cn-i-yvqzo4lhg5/2369ec8805374a939f9a0df994d8baec~noop.image?x-expires=1988788630&x-signature=gIHlONM%2FxU6pxeATGtFHVuDyOsc%3D "xiansuo_API_pic4.png")

#### 4.4 数据回传

1. 在页面中确定拼接了参数后的落地页url
2. 无需输入uid，无需打开手机预览营销，直接模拟手机环境，在页面中点击营销，进入落地页进行操作。如：正常提交一次表单。
3. 将用户行为和拼接了参数的落地页url进行匹配，回传转化数据至回调地址

![xiansuo_API_pic5.png](https://p6-business-sign.byteadimg.com/tos-cn-i-yvqzo4lhg5/c5a7394e0de24314a93a89b9f8918881~noop.image?x-expires=1988788631&x-signature=lgd6IfsrDIGR3u3HPrc6MG1x8gw%3D "xiansuo_API_pic5.png")

### 5、FAQ

**Q： 该联调过程是否一定需要客户的技术人员参与？**

A： 是的。该对接过程需要客户配合开发，在激活联调过程中，需确认客户能够正常接收clickid，成功匹配落地页中表单提交事件，并成功回传事件。

\*\*Q：回传后始终显示不成功怎么办？\*\*

A：首先检测您的回调链接是否写错，可以一对一核查每一个字段。接下来查看回传的event\_type是否与选择的转化目标相同（如“有效获客”对应的event\_type=19）