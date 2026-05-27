import { next } from '@vercel/functions';

const PUBLIC_PATHS = new Set(['/api/subscribe', '/api/unsubscribe', '/health']);

function isPublicPath(pathname) {
  const normalized = pathname.endsWith('/') && pathname !== '/'
    ? pathname.slice(0, -1)
    : pathname;
  return PUBLIC_PATHS.has(normalized);
}

function unauthorized() {
  return new Response('Authentication required', {
    status: 401,
    headers: {
      'WWW-Authenticate': 'Basic realm="Newsletter Admin"',
    },
  });
}

export default function middleware(request) {
  const adminPassword = process.env.ADMIN_PASSWORD;
  if (!adminPassword || isPublicPath(new URL(request.url).pathname)) {
    return next();
  }

  const adminUsername = process.env.ADMIN_USERNAME || 'admin';
  const auth = request.headers.get('authorization');
  if (!auth || !auth.startsWith('Basic ')) {
    return unauthorized();
  }

  let decoded = '';
  try {
    decoded = atob(auth.slice('Basic '.length));
  } catch {
    return unauthorized();
  }

  const separator = decoded.indexOf(':');
  if (separator < 0) {
    return unauthorized();
  }

  const username = decoded.slice(0, separator);
  const password = decoded.slice(separator + 1);
  if (username !== adminUsername || password !== adminPassword) {
    return unauthorized();
  }
  return next();
}

export const config = {
  matcher: ['/((?!favicon.ico).*)'],
};
