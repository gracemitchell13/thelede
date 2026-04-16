const { createClient } = require('@supabase/supabase-js');

exports.handler = async (event) => {
  const code = event.queryStringParameters?.code;

  if (!code) {
    return {
      statusCode: 302,
      headers: { Location: '/settings.html?error=missing_code' }
    };
  }

  const supabase = createClient(
    process.env.SUPABASE_URL,
    process.env.SUPABASE_ANON_KEY
  );

  const { data, error } = await supabase.auth.exchangeCodeForSession(code);

  if (error || !data.session) {
    console.error('Auth error:', error);
    return {
      statusCode: 302,
      headers: { Location: '/settings.html?error=auth_failed' }
    };
  }

  const { access_token, refresh_token } = data.session;

  return {
    statusCode: 302,
    headers: {
      Location: `/settings.html#access_token=${access_token}&refresh_token=${refresh_token}&type=signin`
    }
  };
};
