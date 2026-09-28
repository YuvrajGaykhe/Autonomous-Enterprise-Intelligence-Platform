/** A route that threw while rendering shows the error state instead of a blank page. */

import { useRouteError } from 'react-router';

import { ErrorState } from '@/states/states';

export function RouteError() {
  const error = useRouteError();
  return (
    <div className="mx-auto max-w-2xl p-6">
      <ErrorState error={error} />
    </div>
  );
}
