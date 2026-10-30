-- Zanybyte Media Partners — weekly referral performance (parameterized)
-- @report_start DATE, @report_end DATE, @window_days INT (7 = product default, 14 = contract)
-- Tables: your-gcp-project.acme_analytics.partner_referrals, signups, subscriptions

WITH clicks AS (
  SELECT
    ref_click_id,
    partner_code,
    click_ts,
    attribution_window_days,
    signup_id
  FROM `your-gcp-project.acme_analytics.partner_referrals`
  WHERE partner_code LIKE 'zanybyte%'
    AND DATE(click_ts) BETWEEN @report_start AND @report_end
),
attributed AS (
  SELECT
    c.partner_code,
    c.ref_click_id,
    c.signup_id,
    s.user_id,
    s.created_at AS signup_ts
  FROM clicks c
  LEFT JOIN `your-gcp-project.acme_analytics.signups` s
    ON c.signup_id = s.signup_id
  WHERE c.signup_id IS NOT NULL
    AND TIMESTAMP_DIFF(s.created_at, c.click_ts, DAY) <= @window_days
),
trials AS (
  SELECT
    a.partner_code,
    a.user_id,
    MIN(e.event_ts) AS trial_started_ts
  FROM attributed a
  JOIN `your-gcp-project.acme_analytics.events` e
    ON e.user_id = a.user_id
   AND e.event_name = 'trial_started'
   AND e.event_ts >= a.signup_ts
  GROUP BY 1, 2
),
paid AS (
  SELECT
    t.partner_code,
    t.user_id
  FROM trials t
  JOIN `your-gcp-project.acme_analytics.subscriptions` sub
    ON sub.user_id = t.user_id
   AND sub.status IN ('active', 'past_due')
   AND sub.plan_tier != 'trial'
)
SELECT
  partner_code,
  COUNT(DISTINCT ref_click_id) AS clicks,
  COUNT(DISTINCT signup_id) AS signups,
  COUNT(DISTINCT trials.user_id) AS trials_started,
  COUNT(DISTINCT paid.user_id) AS paid_subscriptions
FROM clicks
LEFT JOIN attributed USING (partner_code, ref_click_id, signup_id)
LEFT JOIN trials USING (partner_code, user_id)
LEFT JOIN paid USING (partner_code, user_id)
GROUP BY partner_code
ORDER BY partner_code;
