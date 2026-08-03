import type { Metadata } from "next";
import { LegalPage, P, S } from "@/components/legal";

export const metadata: Metadata = {
  title: "Terms — FPL Edge",
  description: "Terms of use for FPL Edge: an independent, unofficial Fantasy Premier League tool.",
};

export default function TermsPage() {
  return (
    <LegalPage title="Terms of use" updated="2 August 2026">
      <P>
        By using FPL Edge you agree to these terms. If you do not agree, please do not use the
        site.
      </P>

      <S title="What this site is">
        <P>
          FPL Edge is a free, independent tool that produces statistical projections for Fantasy
          Premier League. It is <strong>not affiliated with, endorsed by, or associated with</strong>{" "}
          the Premier League, Fantasy Premier League, the Football Association Premier League
          Limited, or any football club. All club names, colours and trade marks referred to
          remain the property of their respective owners and are used here only to identify teams
          factually. No official kits, badges or crests are reproduced.
        </P>
      </S>

      <S title="No warranty, no guarantee of accuracy">
        <P>
          Everything on this site is provided <strong>&ldquo;as is&rdquo;</strong>, without
          warranties of any kind, express or implied, including fitness for a particular purpose
          and accuracy. Expected points and difficulty ratings are{" "}
          <strong>probabilistic model estimates</strong>, not predictions of fact. They are
          frequently wrong for an individual player or gameweek, and past accuracy does not imply
          future accuracy.
        </P>
        <P>
          We are candid about this: our model&apos;s per-gameweek player ranking is roughly on a
          par with Fantasy Premier League&apos;s own published expected points, and does not beat
          it. The site&apos;s value is the tooling and transparency, not a superior forecast.
        </P>
      </S>

      <S title="Not advice">
        <P>
          Nothing here is financial, investment, betting or gambling advice, and nothing is an
          inducement to gamble. Fantasy Premier League decisions you make using this site are
          entirely your own. If you choose to use this information in connection with any form of
          wagering, you do so at your own risk and are responsible for complying with the law
          where you live.
        </P>
      </S>

      <S title="Availability and third-party data">
        <P>
          The site depends on Fantasy Premier League&apos;s public API, which is undocumented and
          may change, rate-limit or stop working at any time. We give no guarantee of uptime,
          continuity or data freshness, and we may change or withdraw any part of the site without
          notice.
        </P>
      </S>

      <S title="Acceptable use">
        <P>
          Please do not scrape the site at volume, attempt to disrupt or overload it, probe it for
          vulnerabilities, or use it in any unlawful way. We may block access that threatens the
          service or the upstream APIs we rely on.
        </P>
      </S>

      <S title="Intellectual property">
        <P>
          The site&apos;s design, code, written content and the models behind the projections are{" "}
          <strong>© {new Date().getFullYear()} FPL Edge. All rights reserved.</strong> You may use
          the site for your own personal, non-commercial Fantasy Premier League planning. You may
          not copy, redistribute, resell or systematically extract its output without permission.
        </P>
      </S>

      <S title="Limitation of liability">
        <P>
          To the fullest extent permitted by law, we accept no liability for any loss or damage
          arising from your use of, or reliance on, this site or its projections. Nothing in these
          terms limits liability that cannot lawfully be limited.
        </P>
      </S>

      <S title="Changes, governing law and contact">
        <P>
          We may update these terms; the date at the top will change when we do. These terms are
          governed by the laws of{" "}
          <strong>[ADD GOVERNING JURISDICTION BEFORE DEPLOY — e.g. England and Wales]</strong>.
          Questions: <strong>[ADD CONTACT EMAIL BEFORE DEPLOY]</strong>.
        </P>
      </S>
    </LegalPage>
  );
}
