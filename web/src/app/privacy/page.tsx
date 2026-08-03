import type { Metadata } from "next";
import { LegalPage, P, S } from "@/components/legal";

export const metadata: Metadata = {
  title: "Privacy — FPL Edge",
  description: "What FPL Edge does and does not collect. No accounts, no tracking, no database.",
};

export default function PrivacyPage() {
  return (
    <LegalPage title="Privacy" updated="2 August 2026">
      <P>
        FPL Edge has no accounts, no sign-up, no advertising and no analytics or tracking
        scripts. This page describes everything the site does with data, in plain terms.
      </P>

      <S title="What we collect">
        <P>
          <strong>Nothing about you is stored.</strong> The site keeps no database of users and
          sets no tracking cookies.
        </P>
        <P>
          If you enter an <strong>FPL team ID</strong>, it is sent to our server so we can request
          that team&apos;s publicly visible squad from Fantasy Premier League&apos;s public API and
          show you an analysis of it. That ID and the squad it returns are held{" "}
          <strong>in server memory for up to 120 seconds</strong> so repeated views do not
          re-request the same data from FPL, and are then discarded. They are never written to
          disk, never linked to you, and never shared.
        </P>
        <P>
          Your <strong>light/dark theme choice</strong> is stored in your own browser&apos;s local
          storage. It never leaves your device and is not a tracking cookie.
        </P>
      </S>

      <S title="What our hosting providers see">
        <P>
          Like any website, our hosting and content-delivery providers process standard technical
          request logs — IP address, browser user-agent, the page requested and a timestamp — to
          serve the site, keep it available and prevent abuse. We do not use those logs to build
          profiles, and we do not combine them with any FPL team ID.
        </P>
      </S>

      <S title="Legal basis and your rights (UK GDPR / EU GDPR)">
        <P>
          Where the limited processing above involves personal data, we rely on our{" "}
          <strong>legitimate interests</strong> in operating and securing a free tool. Because we
          store nothing about you beyond the transient cache and provider logs described above, we
          normally hold no personal data to give you access to, correct or erase.
        </P>
        <P>
          You still have the right to ask what is held about you, to request correction or
          erasure, to object to processing, and to complain to a supervisory authority — in the UK,
          the Information Commissioner&apos;s Office (ico.org.uk). To exercise any of these,
          contact us at the address below.
        </P>
      </S>

      <S title="Third parties">
        <P>
          To produce projections the site requests public data from Fantasy Premier League
          (fantasy.premierleague.com) and historical results and closing odds from
          Football-Data.co.uk. These requests are made by our server, not your browser, so those
          services do not receive your IP address as a result of your visit. We do not sell or
          share data with anyone.
        </P>
      </S>

      <S title="Children">
        <P>
          The site is not directed at children and we knowingly collect no data from anyone.
        </P>
      </S>

      <S title="Changes and contact">
        <P>
          If this policy changes materially we will update the date at the top of this page.
          Questions or requests: <strong>[ADD CONTACT EMAIL BEFORE DEPLOY]</strong>.
        </P>
      </S>
    </LegalPage>
  );
}
