/**
 * `/` is the office (D-F-6), which F3 builds. Until then it opens Classic view, keeping the query.
 */

import { Navigate, useLocation } from 'react-router';

export function HomeRedirect() {
  const { search } = useLocation();
  return <Navigate to={{ pathname: '/classic', search }} replace />;
}
