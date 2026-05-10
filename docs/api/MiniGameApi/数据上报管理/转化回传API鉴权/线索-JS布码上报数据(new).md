## 适用场景：

客户投放自有落地页，通过在落地页内添加巨量引擎的JS代码来追踪页面内的转化事件。

采用该方式追踪时，您需要在落地页中添加巨量引擎提供的JS代码，代码检测无误后，即可上报转化事件，追踪落地页转化效果。

推荐使用场景：用户转化行为是在客户自有的落地页完成。

## 新建js转化

在营销投放平台找到资产-转化跟踪-新建线索转化-选择使用js布码，填写转化名称、选择转化目标  
![js_pic1.png](https://p6-business-sign.byteadimg.com/tos-cn-i-yvqzo4lhg5/02f6751c817040d7a1a5a01a0a4ea3b1~noop.image?x-expires=1988788602&x-signature=FGV0W%2Fxcy%2BqU14uwAJFYCbtTNmo%3D "js_pic1.png")

![js_pic2.png](https://p26-business-sign.byteadimg.com/tos-cn-i-yvqzo4lhg5/c8a99b77eb514097ae65251bf9de87c6~noop.image?x-expires=1988788602&x-signature=HDygrC6gsTMywBCFrHLZ34I4Cdk%3D "js_pic2.png")

## 安装代码

新建js布码后，平台会给出您需要添加在落地页上的代码。代码分为两部分：

* 基础代码：添加在您落地页的`<head>`与`</head>`之间，用于收集与上报转化行为。注意：所有需要上报转化的页面中都需要添加基础代码。
* 转化代码：添加在用户触发转化行为之后。例如您将某个点击按钮定义为转化行为，那么用户在点击该按钮后，通过执行转化代码来通知基础代码，基础代码收到通知后记录本次转化行为，发送给巨量引擎，记录为一个转化。注意：不支持在iframe中使用转化代码

代码分为两部分：

### 基础代码：

添加在您落地页的`<head>`与`</head>`之间，用于收集与上报转化行为。

```
<!-- Bytedance Tracking -->
<script>function(r,d,s,l){var meteor=r.meteor=r.meteor||[];meteor.methods=["track","off","on"];meteor.factory=function(method){return function(){
  var args=Array.prototype.slice.call(arguments);args.unshift(method);meteor.push(args);return meteor}};for(var i=0;i<meteor.methods.length;i++){
  var key=meteor.methods[i];meteor[key]=meteor.factory(key)}meteor.load=function(){var js,fjs=d.getElementsByTagName(s)[0];js=d.createElement(s);
  js.src="https://analytics.snssdk.com/meteor.js/v1/"+l+"/sdk";fjs.parentNode.insertBefore(js,fjs)};meteor.load();if(meteor.invoked){return}
  meteor.invoked=true;meteor.track("pageview")})(window,document,"script","3526908054");
</script>
<!-- End Bytedance Tracking -->
```

* 注意1：所有需要上报转化的页面中都需要添加基础代码，否则会造成转化上报失败

![js_pic1-2.png](https://p6-business-sign.byteadimg.com/tos-cn-i-yvqzo4lhg5/092b5a09753d4f5caa1ecbf2d21592e1~noop.image?x-expires=1988788602&x-signature=zFOVSiXM%2BI8CVipweVkD9vVzzKo%3D "js_pic1-2.png")

* 注意2：基础代码中的tracking\_id（上图中红色框圈出的部分）在不同账户中的取值不同，如果客户的同一个页面要在不同账户中使用，那么需要把每个账户的基础代码都添加一遍。

### 转化代码：

在客户的代码中，添加在用户触发转化行为之后。例如客户将某个点击按钮定义为转化行为，那么就把转化代码添加在点击按钮的位置。用户实际访问页面时，点击该按钮就会触发转化代码，转化代码会通知基础代码，基础代码收到通知后记录本次转化行为，发送给巨量引擎，记录为一个转化。

`meteor.track("phone", {convert_id: "1659133743570951"})`

* **注意1**：不支持在iframe中使用转化代码
* **注意2**：同一个页面在多条营销计划中用于投放时，可以只创建一个转化跟踪，巨量引擎可以区分出转化来自哪一条营销计划，来自非营销投放的转化会被记为“外部流量”。

![js_pic3-1.png](https://p3-business-sign.byteadimg.com/tos-cn-i-yvqzo4lhg5/3bfbbb6e0a834842936986847955c0a3~noop.image?x-expires=1988788602&x-signature=YPyiwbssvNV57Pa1%2FEZiUe7zg3c%3D "js_pic3-1.png")

* **注意3**：上图中红框圈出的部分分别对应所选转化目标对应的事件名称（例如电话拨打对应phone，表单提交对应form），和当前转化的转化ID（convert\_id），页面添加转化代码时，这两个地方填写错误会导致转化上报失败。同一个页面可以添加多个转化代码，需要注意把所需的事件名称和转化ID都填写正确

## 代码安装示例

* 表单提交

```
<title>转化跟踪</title>
​
    <!-- 安装基础代码 -->
    <!-- Bytedance Tracking -->
    <script>function(r,d,s,l){var meteor=r.meteor=r.meteor||[];meteor.methods=["track","off","on"];meteor.factory=function(method){return function(){
        var args=Array.prototype.slice.call(arguments);args.unshift(method);meteor.push(args);return meteor}};for(var i=0;i<meteor.methods.length;i++){
        var key=meteor.methods[i];meteor[key]=meteor.factory(key)}meteor.load=function(){var js,fjs=d.getElementsByTagName(s)[0];js=d.createElement(s);
        js.src="https://analytics.snssdk.com/meteor.js/v1/"+l+"/sdk";fjs.parentNode.insertBefore(js,fjs)};meteor.load();if(meteor.invoked){return}
        meteor.invoked=true;meteor.track("pageview")})(window,document,"script","3526908054");
    </script>
    <!-- End Bytedance Tracking -->
​
​
​
    <form>
        姓名：<input type="text" name="" placeholder="请输入姓名" id="uname">
        地址：<input type="password" placeholder="请输入地址" id="address">
        <input type="button" value="提交表单" id="btn">
    </form>
    <script type="text/javascript">
        window.onload = function () {
​
            var btn = document.getElementById("btn");
            var uname = document.getElementById("uname");
            var address = document.getElementById("address");
            // 点击提交表单按钮 
            btn.addEventListener("click", function () {
                var xhr = new XMLHttpRequest();
                xhr.onreadystatechange = function () {
                    if (xhr.readyState == 4 && xhr.status == 200) {
​
                        var data = JSON.parse(xhr.responseText);
                        // 判断表单正确提交成功后执行转化代码
                        if (data.status == "success") {
                            alert("表单提交成功");
​
                            // 安装转化代码
                            meteor.track("form", { convert_id: "1234567890" })
​
                        }
                    }
                    xhr.open("GET", "path/to/file" + uname.value + "&address=" + address.value + "", true);
                    xhr.send();
                }
            })
        }
    </script>
```

* 微信复制

```
<title></title>
    <script type="text/javascript" src="http://ajax.aspnetcdn.com/ajax/jquery/jquery-2.1.1.min.js"></script>
    <script type="text/javascript" src="http://s3.pstatp.com/inapp/toutiao.js"></script>
​
    <!-- 安装基础代码 -->
    <!-- Bytedance Tracking -->
    <script>function(r,d,s,l){var meteor=r.meteor=r.meteor||[];meteor.methods=["track","off","on"];meteor.factory=function(method){return function(){
        var args=Array.prototype.slice.call(arguments);args.unshift(method);meteor.push(args);return meteor}};for(var i=0;i<meteor.methods.length;i++){
        var key=meteor.methods[i];meteor[key]=meteor.factory(key)}meteor.load=function(){var js,fjs=d.getElementsByTagName(s)[0];js=d.createElement(s);
        js.src="https://analytics.snssdk.com/meteor.js/v1/"+l+"/sdk";fjs.parentNode.insertBefore(js,fjs)};meteor.load();if(meteor.invoked){return}
        meteor.invoked=true;meteor.track("pageview")})(window,document,"script","123456789");
      </script>
    <!-- End Bytedance Tracking -->
​
​
​
    
    <div>
        <span>请长按复制</span>
        <!-- 当页面有多个微信号时 每个微信号都要绑定复制事件 -->
        <span class="wei_xin">jkl83123</span>
        <span class="wei_xin">jkl83123</span>
        <span class="wei_xin">jkl83123</span>
    </div>
    <script type="text/javascript">
​
       // jquery方式：
        $(".wei_xin").bind('copy', function(e) {
            alert("复制成功");
​
            // 复制成功后 执行转化代码 
            meteor.track("wechat", { convert_id: "1234567890" })
​
        });
​
        /** js方式
        var weixin = document.getElementsByClassName("wei_xin");
        var len = weixin.length;
        for (var i = 0;i < len;i++) {
            weixin[i].i = i;
            weixin[i].addEventListener("copy", function() {
                alert(this.i + "复制成功");
​
                // 复制成功后 安装转化代码
                meteor.track("wechat", { convert_id: "1234567890" })
​
            });
        }
        */
    </script>
```

## 代码检测

安装完代码后，您可通过“检测转化上报”功能来判断是否正确安装。  
![js_pic3.png](https://p6-business-sign.byteadimg.com/tos-cn-i-yvqzo4lhg5/ecb2ab5e2dd04243a870b0ba22753557~noop.image?x-expires=1988788602&x-signature=vZPqdU6%2BL53LDDgiWYMxlypWgxw%3D "js_pic3.png")

检测转化上报有两个步骤，分别是检测页面页面基础代码和检测页面转化代码，完成后即联调成功  
![js_pic4.png](https://p6-business-sign.byteadimg.com/tos-cn-i-yvqzo4lhg5/8589df5022f547c689e05001ea78a2ae~noop.image?x-expires=1988788602&x-signature=SolkNcFV7l2CP9EJ5xdAq7kJW8k%3D "js_pic4.png")  
![js_pic5.png](https://p3-business-sign.byteadimg.com/tos-cn-i-yvqzo4lhg5/4050ecb6ddf24a1a8238c52110015592~noop.image?x-expires=1988788602&x-signature=RJ9FvJ%2FGNpePqHmn19eKRShpfHA%3D "js_pic5.png")

* **基础代码添加不正确的常见原因：**

1. 代码添加位置不正确，未加在`<head>`与`</head>`之间，需调整代码
2. 未完全参照所提供的基础代码，存在书写错误，需检查代码内容
3. 页面代码存在报错，影响基础代码的加载，需要修复报错问题
4. 基础代码被嵌套在iframe中（不支持的使用方式，需更换使用方法）
5. tracking\_id不符。每个账户的JS基础代码有专属的tracking\_id（位于基础代码中，如下图所示），如果落地页需要跨账户使用，建议在落地页中将每个账户的基础代码都添加一次。

![js_pic6.png](https://p26-business-sign.byteadimg.com/tos-cn-i-yvqzo4lhg5/4718239e7061408dbc61f87653c13ac9~noop.image?x-expires=1988788602&x-signature=FFE18SZnpY5BQV7k1tz1G%2BE1ILA%3D "js_pic6.png")

* **转化代码添加不正确的常见原因：**

1. 转化ID（convert\_id）不符：例如您上报的转化ID为12345，但正确的转化ID为67890，需修改代码，上报正确的转化ID
2. 转化事件（event\_type）不符：例如您上报的转化事件为button，但选定转化目标为phone，需修改代码，上报正确的转化事件
3. 页面存在跳转，跳转后的页面未正确安装基础代码，需要在每个上报转化的页面上都添加基础代码
4. 转化代码未放置在转化执行的位置，代码未生效或生效时机有误，需修改代码（技术人员可在添加转化代码的位置加埋点，确认发生转化行为时，代码是否正确执行到此处）
5. 基础代码的生效时机晚于转化代码，需修改代码
6. 转化代码被嵌套在iframe中（不支持的使用方式），需修改代码

* **如客户修改代码需要重新进行联调**

## 常见问题

**Q1:【数据gap】营销投放平台转化数比客户统计的转化数多**

* 一般是客户转化代码埋点位置不对 或者 客户统计的与巨量引擎统计的口径不一致。例：

1. 客户把成功提交表单作为一次转化并统计，而转化代码却埋点在提交按钮的点击上，所以巨量引擎统计的是埋点的位置也就是提交按钮点击的转化数，与客户统计的表单提交数不一致。此类情况，是客户埋转化代码的位置不对造成，可在添加转化代码的位置加埋点，以便查找转化上报与转化统计不一致的原因
2. 选择微信复制作为转化目标的客户，经常用微信号的复制数与实际加粉数做对比。首先客户如果埋点在微信号的复制上，那就应该用他们收集的复制数据来和营销投放平台的数据做对比，而不是实际的加粉数，实际的加粉数和复制的数量是两个概念，不能对比。
3. 客户突然转化数突增爆量导致转化率高消耗很高，一般是因为客户修改了页面，造成转化突然增长。

**Q2:【数据gap】营销投放平台转化数比客户统计的转化数少或不稳定（有时正常有时数量少）**

* 一般是客户统计的与巨量引擎统计的口径不一致。例：

1. 客户的统计的口径是所有来源（包括浏览器或其他平台）的转化数，没有区分是否是来自营销投放平台的转化数。我们统计的是在投放app内产生的转化，如果在非营销环境内产生的转化，我们计作外部流量，而不计作有效转化。
2. 客户统计是通过投放的url上的某个参数来判断转化是否来自巨量引擎。注意：这种判断方式是不准确的，即使这个url是投放在平台，也是无法确定转化是否在平台内产生的，比如带有该参数的链接被用户分享出去，并在其他app内产生了转化，这种情况营销投放平台会算作外部流量，而客户会算作是营销投放平台带来的转化，因此产生数据的gap。
3. 营销投放平台统计有效转化规则较严格：同一个用户在一次营销展示中产生多次转化只算作一次，同一用户在7天内浏览到同一营销并产生转化只算一次。所以在某些场景下，例如用户两次提交表单，客户算两次而营销投放平台只算一次。

\*\*Q3:【联调问题】为什么在检测转化上报过程中显示代码安装有误，但实际投放时转化数据没有问题？\*\*

* 检测转化上报功能是为了帮助检测代码安装情况，但是可能会因为页面结构和设置问题，导致无法正常检测。如果实际投放时转化数据没有问题，可跳过检测过程。