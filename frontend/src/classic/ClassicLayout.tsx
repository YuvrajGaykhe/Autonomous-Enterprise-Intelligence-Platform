/** Classic view: the same data as the office, as plain pages (D-F-6, spec §8.1). */

import { NavLink, Outlet, useLocation } from 'react-router';

import { cn } from '@/lib/utils';

export function ClassicLayout() {
  const { search } = useLocation();
  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-4 md:flex-row">
      <nav aria-label="Classic view" className="md:w-48 md:shrink-0">
        <ul className="flex gap-2 md:flex-col">
          <li>
            <NavLink
              end
              to={{ pathname: '/classic', search }}
              className={({ isActive }) =>
                cn('block rounded-md px-3 py-1.5 text-sm', isActive ? 'bg-muted font-medium' : '')
              }
            >
              Overview
            </NavLink>
          </li>
        </ul>
      </nav>
      <div className="min-w-0 flex-1">
        <Outlet />
      </div>
    </div>
  );
}
