**xpath**是一种无需开发成本的落地页跟踪方式，采用该方式跟踪时，您无需在落地页中添加代码，只需要在平台填写落地页链接，并在模拟出来的页面上设置转化路径（当触发页面某个位置时定义为转化），即可完成转化事件上报，跟踪落地页转化效果。

推荐使用场景：用户转化行为是在落地页完成。

xpath有跟踪用户点击事件和用户访问事件两类，请根据使用场景进行选择：  
![Xpath_pic1.png](https://p6-business-sign.byteadimg.com/tos-cn-i-yvqzo4lhg5/6ee5bc0179f146ee99ef8f7e0b797d43~noop.image?x-expires=1988788655&x-signature=Czbfy7aFglnZwERnX46rA9GtM%2Fg%3D "Xpath_pic1.png")

### 1、跟踪用户点击事件-创建流程（[功能入口](https://ad.toutiao.com/conversion/track/xpath/write-url)）

#### 1.1 用户点击事件-普通创建流程

**（1）填写落地页链接，例如**`https://m.toutiao.com/?from=123&utm=456`**，点击“显示页面**  
![Xpath_pic2.png](https://p3-business-sign.byteadimg.com/tos-cn-i-yvqzo4lhg5/4464e924002f4106bc03e3d8a5dd4bc6~noop.image?x-expires=1988788656&x-signature=Po25AQ4oL9tAK5sQMuDaQj%2Ba8Ck%3D "Xpath_pic2.png")

**（2）营销后台渲染出对应的页面结构，您可通过点击目标区域来设置转化路径**

* **匹配规则：** 实际投放中，用户在相同页面完成相同行为时，可记为有效转化。例如客户在新建转化时填写的链接是`https://m.toutiao.com/?from=123&utm=456`，用户也需要打开一模一样的链接。对于链接中包含参数的情况，可以选择是否要忽略指定参数，示例链接中可选择是否忽略from和utm的取值。假设选择只忽略from，则用户实际打开`https://m.toutiao.com/?from=789&utm=456`，或`https://m.toutiao.com/?utm=456`，均可记为相同页面，但打开`https://m.toutiao.com/?from=123&utm=321`时，不记为相同页面。
* **转化生效的条件：** 实际投放中，用户在相同页面完成相同行为时，可记为有效转化。

* **条件1：** 用户在头条系app的营销环境中打开页面（例如头条信息流、抖音信息流等）。非头条系营销环境下，我们无法获取用户点击行为。
* **条件2：** 用户访问客户填写的相同的落地页链接。客户可选择忽略链接中的参数（详见匹配规则）
* **条件3：** 用户产生相同的xpath路径（完成相同行为）。例如设置点击“购买”按钮的路径为div1>div2>div3，实际操作时该路径变为div1>div2>div3>div4，则会导致匹配失败，请与页面开发者联系，尽量避免按钮路径的变化。

#### 1.2 用户点击事件-使用xpath工具创建流程

对于页面结构复杂导致后台渲染失败，或者需要设置的转化行为在跳转页面或弹窗中的情况，推荐使用xpath工具进行转化设置。 [旧版下载链接](https://tosv.byted.org/obj/meteor-static/bytedance_track_xpath.zip) [新版下载链接](https://tosv.byted.org/obj/meteor-static/bytedance_track_xpath.zip)-2019.04.03更新 [新版下载链接](https://lf6-ttcdn-tos.pstatp.com/obj/meteor-static/bytedance_track_xpath.zip)-2019.09.09更新（推荐使用最新版本）

#### 1.3 Xpath插件操作方法

安装方法：

* 在 Chrome 浏览器中进入开发者模式  
  ![Xpath_pic4.png](https://p3-business-sign.byteadimg.com/tos-cn-i-yvqzo4lhg5/2eb548cad30645cc94eff300e5c1f9d2~noop.image?x-expires=1988788655&x-signature=q%2BsMjZOoxh%2FsqN8EEIxD01fDqdQ%3D "Xpath_pic4.png")
* 点击[新版下载链接-2019.09.09更新](https://lf6-ttcdn-tos.pstatp.com/obj/meteor-static/bytedance_track_xpath.zip)下载插件并解压缩  
  ![Xpath_pic5.png](https://p3-business-sign.byteadimg.com/tos-cn-i-yvqzo4lhg5/f37a2b56f525430f9abc9245ab721c90~noop.image?x-expires=1988788655&x-signature=JUdPZKXr9oFhTUaHFu7Fd3DvAYY%3D "Xpath_pic5.png")
* 将解压缩后的文件夹拖入 Chrome 中的拓展程序页面安装（一定注意是解压后的文件夹）  
  ![Xpath_pic6.png](https://p6-business-sign.byteadimg.com/tos-cn-i-yvqzo4lhg5/b8fb6203e82d4adda6bfa5c8e91a3428~noop.image?x-expires=1988788655&x-signature=aa6y6ug8uPZ6vAMeNZGpxAmzzUo%3D "Xpath_pic6.png")
* 确认安装完成：安装完成后，浏览器右上会出现 T 字的角标（使用注意，该种方式下浏览器偶尔会自动关闭该插件，进入设置－扩展程度点击‘打开’重新启用即可）  
  ![Xpath_pic7.png](https://p26-business-sign.byteadimg.com/tos-cn-i-yvqzo4lhg5/19edfac908334058b1a13cda8620b229~noop.image?x-expires=1988788655&x-signature=8rWTtjMRF2ChOoaVVpQ39IDDbH8%3D "Xpath_pic7.png")
* 插件开启的情况下，设置转化跟踪时，在插件输入需要追踪的url，并在弹出的浏览器页面中进行设置：右键点击需要的转化区域，再点击进入转化设置即可完成设置  
  ![Xpath_pic8.png](https://p3-business-sign.byteadimg.com/tos-cn-i-yvqzo4lhg5/f9d42a60846042a589af27ef09deec7f~noop.image?x-expires=1988788656&x-signature=CgLdwM9mI2GVZU4qX9XRt2Ykjh8%3D "Xpath_pic8.png")
* 成功安装xpath工具后，填写落地页链接并点击“显示页面”，会弹出新窗口，鼠标左键点击可操作页面跳转，右键点击设置转化区域。完成后点击“进入转化设置”，之后操作与普通创建流程相同  
  ![Xpath_pic9.png](https://p3-business-sign.byteadimg.com/tos-cn-i-yvqzo4lhg5/4757effa1c2049a2bbb8c0f1ad62d0f0~noop.image?x-expires=1988788656&x-signature=J5arsMDwWZ%2B1oaNzC81JtTPGH8o%3D "Xpath_pic9.png")

**说明：使用xpath工具时，如果有页面跳转，落地页链接以跳转后的链接为准，其他规则同普通创建流程。**

#### 1.4 推荐使用场景

追踪用户是否点击指定页面的按钮或者热区，例如用户是否点击页面中的提交按钮。

### 2、跟踪用户访问事件-创建流程：（[功能入口](https://ad.toutiao.com/conversion/track/xpath/create-view)）

#### 2.1 输入转化名称与目标页面

![Xpath_pic10.png](https://p6-business-sign.byteadimg.com/tos-cn-i-yvqzo4lhg5/3ec3b359fe704a5bb78f4d0d7aa06fcf~noop.image?x-expires=1988788656&x-signature=zYzMQUik%2BaP0SIpoEHsfGk7QXSc%3D "Xpath_pic10.png")

#### 2.2 匹配规则：

实际投放中，用户在相同页面完成相同行为时，可记为有效转化。例如客户在新建转化时填写的链接是`https://m.toutiao.com/?from=123&utm=456`，用户也需要打开一模一样的链接。对于链接中包含参数的情况，可以选择是否要忽略指定参数，示例链接中可选择是否忽略from和utm的取值。假设选择只忽略from，则用户实际打开`https://m.toutiao.com/?from=789&utm=456`，或`https://m.toutiao.com/?utm=456`，均可记为相同页面，但打开`https://m.toutiao.com/?from=123&utm=321`时，不记为相同页面。

#### 2.3 转化生效的条件：

实际投放中，用户到达相同页面。

* **条件1**：用户在头条系app的营销环境中打开页面（例如头条信息流、抖音信息流等）。
* **条件2**：用户访问客户填写的相同的落地页链接。客户可选择忽略链接中的参数（详见匹配规则）

#### 2.4 推荐场景：

落地页一跳url与目标url的域名或路径不同。例如一跳链接为`https://m.toutiao.com/`，目标url为`https://m.toutiao.com/abc/def`。以表单提交为目标的页面，如果表单提交成功页有特定的url路径，可将成功页的url设置为目标。

### 3、跟踪用户点击事件-常见问题

**1）、xpath设置完成后，转化跟踪显示“活跃”，为什么实际上一个有效转化也没有收到？**

* xpath对应的转化会默认显示“活跃”状态。需要自行判断转化是否能上报成功。
* 判断方法：创建营销计划，选择您创建的xpath转化跟踪。预览营销计划，并在手机端完成您设置的行为，查看数据是否上报成功。

**2）、xpath是否支持悬浮按钮的点击跟踪？**

* 可新建转化，创建营销计划进行测试，以测试结果为准。

**3）、xpath出现页面加载不出，解析渲染不出内容，是怎么回事？**

* **排查方向1** 请参考下图提示，是由于xpath不支持二跳，所以无法识别，需要提供最终落地页链接。  
  ![Xpath_pic11.png](https://p6-business-sign.byteadimg.com/tos-cn-i-yvqzo4lhg5/371e778c4c7f4a17ad62541cd5c632a6~noop.image?x-expires=1988788656&x-signature=5aMvVQwYIoZWQakaFsDVVisUQnA%3D "Xpath_pic11.png")
* **排查方向2** 对于页面结构复杂导致后台渲染失败的，或者需要设置的转化行为在跳转页面或弹窗中的情况，推荐使用xpath工具进行转化设置。 [新版下载链接-2019.09.09更新](https://lf6-ttcdn-tos.pstatp.com/obj/meteor-static/bytedance_track_xpath.zip)

**4）、【数据gap】为什么使用xpath追踪到的转化数小于实际转化数？**

* 常见原因：

1. 创建转化跟踪时设置的url与实际打开时不一致，例如url上参数值发生变化，或者使用了编码格式的url。此时建议联系页面开发人员保证页面url与创建时一致，或者重新创建转化跟踪用于投放。
2. 页面结构比较复杂，在不同条件下，相同点击区域的xpath路径不完全相同，导致部分转化无法匹配到。此时建议与页面开发者联系，获取到各种可能的xpath路径。

**5）、【数据gap】为什么使用xpath追踪到的转化数大于实际的转化数？**

1. xpath转化跟踪方式存在局限性，只能监测页面到达和页面点击事件，可能无法代表真实的目标事件。例如您设置点击“立即报名”按钮为转化目标，上报的转化数很可能大于表单提交成功的用户数量。如需更准确的监测方式，推荐使用JS布码或线索API方式进行转化跟踪。

### 4、跟踪用户访问事件-常见问题

* **xpath设置完成后，转化跟踪显示“活跃”，为什么实际上一个有效转化也没有收到？**

1. xpath对应的转化会默认显示“活跃”状态。需要自行判断转化是否能上报成功。
2. 判断方法：创建营销计划，选择您创建的xpath转化跟踪。预览营销计划，并在手机端完成您设置的行为，查看数据是否上报成功。

* **用户在任何情况下到达目标页面，都会被记入转化吗？**
* 仅当用户在头条营销环境中到达目标页面时，才会被记为转化。

* **【数据gap】为什么使用xpath追踪到的转化数小于实际转化数？**
* 常见原因：创建转化跟踪时设置的url与实际打开的url不一致，请仔细检查所设置的目标页面与实际情况是否相同。