import React from 'react';
import { Bell } from 'lucide-react';

function notificationText(n) {
  if (n.type === 'order') {
    return `${n.customer} ne ${n.product} (₹${n.price}) ka order confirm kiya hai.`;
  }
  return `${n.customer} aapse baat karna chahti hain.`;
}

export default function NotificationBell({ notifications, isOpen, onToggle, onMarkRead }) {
  const unreadCount = notifications.filter((n) => !n.read).length;

  return (
    <div className="relative">
      <button
        onClick={onToggle}
        className="relative text-meesho-jamuni hover:text-meesho-pink border border-transparent p-1.5 rounded-full hover:bg-white transition active:translate-y-[1px]"
        title="Notifications"
      >
        <Bell className="w-4 h-4" />
        {unreadCount > 0 && (
          <span className="absolute -top-0.5 -right-0.5 w-4 h-4 flex items-center justify-center rounded-full bg-[#FC8B16] text-white text-[9px] font-bold leading-none border border-meesho-dark">
            {unreadCount > 9 ? '9+' : unreadCount}
          </span>
        )}
      </button>

      {isOpen && (
        <div
          className="absolute right-0 top-full mt-2 w-72 max-h-80 overflow-y-auto z-[300]
            bg-[#F7F7FA] rounded-[0.5rem] shadow-lg border border-gray-200"
        >
          <div className="px-3 py-2 border-b border-gray-200">
            <span className="text-xs font-bold text-meesho-dark">Notifications</span>
          </div>

          {notifications.length === 0 ? (
            <p className="px-3 py-4 text-xs text-gray-500 text-center">
              Koi nayi notification nahi hai.
            </p>
          ) : (
            <div className="p-2 space-y-2">
              {notifications.map((n) => (
                <button
                  key={n.id}
                  onClick={() => onMarkRead(n.id)}
                  className={`w-full text-left bg-white rounded-[0.5rem] border-b border-gray-200 px-3 py-2 transition ${
                    n.read ? 'opacity-50' : 'opacity-100'
                  }`}
                >
                  <p className="text-xs text-meesho-dark leading-snug">{notificationText(n)}</p>
                </button>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
