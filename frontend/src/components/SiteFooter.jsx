// 外链统一在新窗口打开，并加 noopener，避免被目标页拿到 window.opener
const EXTERNAL = [
  {
    title: '监管与规则',
    links: [
      ['港交所上市规则', 'https://www.hkex.com.hk/Listing/Rules-and-Guidance/Listing-Rules?sc_lang=zh-HK'],
      ['披露易（公司公告）', 'https://www.hkexnews.hk/'],
      ['香港证监会', 'https://www.sfc.hk/'],
      ['香港公司注册处', 'https://www.cr.gov.hk/'],
    ],
  },
  {
    title: '港股市场',
    links: [
      ['香港交易所', 'https://www.hkex.com.hk/?sc_lang=zh-HK'],
      ['市场数据（股价/市值）', 'https://www.hkex.com.hk/Market-Data?sc_lang=zh-HK'],
      ['恒生指数公司', 'https://www.hsi.com.hk/'],
      ['投资者及理财教育委员会', 'https://www.ifec.org.hk/'],
      ['香港金融管理局', 'https://www.hkma.gov.hk/'],
    ],
  },
  {
    title: '尽调数据源',
    links: [
      ['国家企业信用信息公示系统', 'https://www.gsxt.gov.cn/'],
      ['信用中国', 'https://www.creditchina.gov.cn/'],
      ['执行信息公开网', 'http://zxgk.court.gov.cn/'],
      ['裁判文书网', 'https://wenshu.court.gov.cn/'],
      ['破产重整案件信息网', 'https://pccz.court.gov.cn/'],
    ],
  },
  {
    title: '披露与行业',
    links: [
      ['巨潮资讯', 'http://www.cninfo.com.cn/'],
      ['中国证监会', 'http://www.csrc.gov.cn/'],
      ['国家知识产权局', 'https://www.cnipa.gov.cn/'],
    ],
  },
]

export default function SiteFooter() {
  return (
    <footer className="site-footer">
      <div className="footer-inner">
        <div className="footer-cols">
          {EXTERNAL.map((group) => (
            <div className="footer-col" key={group.title}>
              <h4>{group.title}</h4>
              <ul>
                {group.links.map(([label, href]) => (
                  <li key={href}>
                    <a href={href} target="_blank" rel="noopener noreferrer">{label}</a>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </div>

      <div className="footer-bottom">
        <span>机器辅助整理，不构成法律意见；结论须经律师复核</span>
        <span className="muted">外部链接指向官方站点，内容以该站点为准</span>
      </div>
    </footer>
  )
}
