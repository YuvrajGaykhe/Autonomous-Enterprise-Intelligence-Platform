import { Link, useLocation } from 'react-router';

export function NotFound() {
  const { search } = useLocation();
  return (
    <div className="mx-auto max-w-2xl space-y-3">
      <h1 className="text-xl font-semibold">Page not found</h1>
      <p className="text-sm">No page lives at this address.</p>
      <Link className="text-sm underline" to={{ pathname: '/classic', search }}>
        Go to Classic view
      </Link>
    </div>
  );
}
